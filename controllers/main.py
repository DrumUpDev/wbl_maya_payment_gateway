# -*- coding: utf-8 -*-
#
#################################################################################
# Author      : Weblytic Labs Pvt. Ltd. (<https://store.weblyticlabs.com/>)
# Copyright(c): 2023-Present Weblytic Labs Pvt. Ltd.
# All Rights Reserved.
#
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
##################################################################################

# -*- coding: utf-8 -*-
import base64
import hashlib
import json
import logging

import requests
from psycopg2 import IntegrityError
from werkzeug.exceptions import BadRequest, NotFound
from werkzeug.utils import redirect
from werkzeug.wrappers import Response

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class MayaController(http.Controller):

    @staticmethod
    def _json_response(payload, status=200):
        return Response(
            json.dumps(payload),
            status=status,
            content_type="application/json; charset=utf-8",
        )

    @staticmethod
    def _build_event_key(headers, scenario, payload, raw_body):
        """
        Idempotency key:
        1) Prefer event/request ids from headers
        2) Fallback deterministic hash
        """
        header_key = (
            headers.get("X-Maya-Event-Id")
            or headers.get("X-Request-Id")
            or headers.get("X-Correlation-Id")
            or headers.get("Idempotency-Key")
        )
        if header_key:
            return header_key.strip()

        checkout_id = (
            payload.get("checkoutId")
            or payload.get("id")
            or payload.get("paymentTransactionReferenceNo")
            or payload.get("requestReferenceNumber")
            or ""
        )
        seed = f"{scenario}|{checkout_id}|".encode("utf-8") + (raw_body or b"")
        return hashlib.sha256(seed).hexdigest()

    @http.route(['/payment/maya/redirect'], type='http', auth='public', website=True)
    def maya_redirect(self, **post):
        """
        Create checkout and redirect customer to Maya hosted page.
        """
        tx_id = post.get('tx_id')
        try:
            tx_id = int(tx_id)
        except (TypeError, ValueError):
            raise NotFound()

        tx = request.env['payment.transaction'].sudo().browse(tx_id)
        if not tx.exists() or tx.provider_id.code != 'maya':
            raise NotFound()

        provider = tx.provider_id.sudo()

        if tx.amount <= 0:
            raise BadRequest("Invalid transaction amount.")

        if tx.currency_id.name != 'PHP':
            raise BadRequest("Maya only supports PHP transactions.")

        if not provider.maya_public_key:
            raise BadRequest("Maya public key is not configured.")

        url = "%s/checkout/v1/checkouts" % provider._maya_get_api_base_url()
        timeout = provider.maya_api_timeout or 30

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Basic " + base64.b64encode((provider.maya_public_key + ":").encode()).decode(),
        }

        payload = {
            "totalAmount": {
                "value": round(float(tx.amount), 2),
                "currency": tx.currency_id.name,
            },
            "buyer": {
                "firstName": tx.partner_id.name or "",
                "contact": {
                    "email": tx.partner_id.email or "",
                    "phone": tx.partner_id.phone or "",
                },
            },
            "requestReferenceNumber": tx.reference,
            "redirectUrl": {
                "success": request.httprequest.host_url + "payment/maya/success?tx_id=%s" % tx.id,
                "failure": request.httprequest.host_url + "payment/maya/failure?tx_id=%s" % tx.id,
                "cancel": request.httprequest.host_url + "payment/maya/cancel?tx_id=%s" % tx.id,
            },
        }

        _logger.info("Maya checkout request tx=%s ref=%s", tx.id, tx.reference)

        try:
            res = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
        except requests.RequestException:
            _logger.exception("Maya checkout API unreachable tx=%s", tx.id)
            raise BadRequest("Could not reach Maya API.")

        _logger.info("Maya checkout response tx=%s status=%s", tx.id, res.status_code)

        try:
            response_data = res.json()
        except ValueError:
            _logger.error("Maya checkout response is not JSON tx=%s body=%s", tx.id, res.text)
            raise BadRequest("Invalid response from Maya API.")

        if res.status_code not in (200, 201):
            raise BadRequest(response_data.get("message") or "Maya checkout failed.")

        checkout_id = response_data.get("checkoutId")
        redirect_url = response_data.get("redirectUrl")
        if not checkout_id or not redirect_url:
            raise BadRequest("Maya response missing checkoutId or redirectUrl.")

        # Keep checkout id, but DO NOT set provider_reference/final state here.
        tx.write({
            'maya_checkout_id': checkout_id,
            'maya_transaction_id': checkout_id,  # backward compatibility
            'maya_status': 'checkout_created',
        })

        return redirect(redirect_url, code=302)

    @http.route(
        ['/payment/maya/success', '/payment/maya/failure', '/payment/maya/cancel'],
        type='http',
        auth='public',
        website=True
    )
    def maya_callback(self, **post):
        """
        Browser return URL only.
        Do NOT set done/canceled here.
        Webhook is source of truth.
        """
        tx_id = post.get('tx_id')
        try:
            tx_id = int(tx_id)
        except (TypeError, ValueError):
            return request.redirect('/payment/status')

        tx = request.env['payment.transaction'].sudo().browse(tx_id)
        if not tx.exists() or tx.provider_id.code != 'maya':
            return request.redirect('/payment/status')

        if "success" in request.httprequest.path:
            redirect_state = "redirect_success"
        elif "failure" in request.httprequest.path:
            redirect_state = "redirect_failure"
        else:
            redirect_state = "redirect_cancel"

        tx.write({'maya_status': redirect_state})
        if tx.state == 'draft':
            tx._set_pending()

        return request.redirect('/payment/status')

    @http.route(
        [
            '/payment/maya/webhook',
            '/payment/maya/webhook/<string:topic>/<string:status>',
        ],
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False
    )
    def maya_webhook(self, topic=None, status=None, **kwargs):
        """
        Server-to-server webhook endpoint with:
        - verification
        - idempotency
        - tx lock
        - safe state transitions
        """
        raw_body = request.httprequest.get_data(cache=False) or b'{}'
        headers = request.httprequest.headers

        try:
            payload = json.loads(raw_body.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            return self._json_response({"ok": False, "error": "Malformed JSON"}, status=400)

        if not isinstance(payload, dict):
            return self._json_response({"ok": False, "error": "Payload must be a JSON object"}, status=400)

        tx_model = request.env['payment.transaction'].sudo()
        provider_model = request.env['payment.provider'].sudo()
        event_model = request.env['maya.webhook.event'].sudo()

        route_scenario = None
        if topic and status:
            route_scenario = "%s_%s" % (topic, status)
        elif request.httprequest.args.get('scenario'):
            route_scenario = request.httprequest.args.get('scenario')

        scenario = tx_model._maya_extract_scenario(payload, default_scenario=route_scenario)

        provider = provider_model._maya_find_provider_for_webhook(headers=headers, raw_body=raw_body)
        if not provider:
            _logger.warning("Maya webhook verification failed scenario=%s", scenario)
            return self._json_response({"ok": False, "error": "Invalid signature/auth"}, status=401)

        event_key = self._build_event_key(headers, scenario, payload, raw_body)

        try:
            webhook_event = event_model.create({
                'event_key': event_key,
                'provider_id': provider.id,
                'scenario': scenario or '',
                'state': 'received',
                'payload': json.dumps(payload, ensure_ascii=False),
            })
        except IntegrityError:
            request.env.cr.rollback()
            _logger.info("Maya webhook duplicate ignored event_key=%s", event_key)
            return self._json_response({"ok": True, "duplicate": True}, status=200)

        try:
            tx = tx_model._maya_resolve_from_webhook_payload(payload)
            if not tx:
                webhook_event.write({
                    'state': 'ignored',
                    'processing_message': 'No matching transaction found.',
                })
                return self._json_response({"ok": True, "processed": False, "reason": "no_transaction"}, status=200)

            # Lock tx row to avoid concurrent scenario races
            request.env.cr.execute(
                "SELECT id FROM payment_transaction WHERE id = %s FOR UPDATE SKIP LOCKED",
                (tx.id,),
            )
            if not request.env.cr.fetchone():
                webhook_event.write({
                    'state': 'ignored',
                    'transaction_id': tx.id,
                    'processing_message': 'Transaction is currently being processed.',
                })
                return self._json_response({"ok": True, "processed": False, "reason": "locked"}, status=200)

            result = tx._maya_apply_webhook_scenario(scenario, payload)

            webhook_event.write({
                'transaction_id': tx.id,
                'state': 'processed',
                'processing_message': result,
            })

            _logger.info("Maya webhook processed event_key=%s tx=%s scenario=%s", event_key, tx.id, scenario)
            return self._json_response({"ok": True, "processed": True, "tx_id": tx.id}, status=200)

        except Exception as exc:
            _logger.exception("Maya webhook processing error event_key=%s", event_key)
            webhook_event.write({
                'state': 'error',
                'processing_message': str(exc)[:500],
            })
            return self._json_response({"ok": False, "error": "Processing error"}, status=500)


