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

from odoo import http
from odoo.http import request
import json
import base64
import requests
import logging
from werkzeug.utils import redirect

logger = logging.getLogger(__name__)


class MayaController(http.Controller):
    # When I click on paynow on cart page then redirct this function. It has two api one for sandbox and another for production.
    @http.route(['/payment/maya/redirect'], type='http', auth='public', website=True)
    def maya_redirect(self, **post):
        tx_id = post.get('tx_id')
        tx = request.env['payment.transaction'].sudo().browse(int(tx_id))

        # It's decided api url which url enabled like sandbox for testing mode and production for live
        provider = tx.provider_id
        if provider.state == "enabled":
            url = "https://pg.paymaya.com/checkout/v1/checkouts"
        else:
            url = "https://pg-sandbox.paymaya.com/checkout/v1/checkouts"

        # Created authorization header public key to base64
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Basic " + base64.b64encode((provider.maya_public_key + ":").encode()).decode(),
        }

        payload = {
            "totalAmount": {
                "value": tx.amount,
                "currency": "PHP",
            },
            "buyer": {
                "firstName": tx.partner_id.name,
                "contact": {
                    "email": tx.partner_id.email,
                    "phone": tx.partner_id.phone
                }
            },
            "requestReferenceNumber": tx.reference,
            "redirectUrl": {
                "success": request.httprequest.host_url + "payment/maya/success?tx_id=" + str(tx.id),
                "failure": request.httprequest.host_url + "payment/maya/failure?tx_id=" + str(tx.id),
                "cancel": request.httprequest.host_url + "payment/maya/cancel?tx_id=" + str(tx.id)
            }
        }
        logger.info(f"payload: {payload}")
        res = requests.post(url, headers=headers, data=json.dumps(payload))
        logger.info(f"res: {res.status_code} {res.text}")

        response_data = res.json()
        logger.info(f"response_data: {response_data}")

        # Save the checkoutId here
        tx.write({
            'maya_transaction_id': response_data.get("checkoutId"),
            'provider_reference': response_data.get("checkoutId"),
        })

        redirect_url = response_data.get("redirectUrl")
        return redirect(redirect_url, code=302)


    @http.route(['/payment/maya/success', '/payment/maya/failure', '/payment/maya/cancel'], type='http', auth='public',
                website=True)
    def maya_callback(self, **post):
        # If url is success than save the currency and status
        tx_id = int(post.get('tx_id'))
        tx = request.env['payment.transaction'].sudo().browse(tx_id)
        if "success" in request.httprequest.path:

            tx._set_done()
            tx.write({
                'maya_currency': "PHP",
                'maya_status': tx.state,
                'provider_reference': tx.maya_transaction_id,
            })
        elif "failure" in request.httprequest.path or "cancel" in request.httprequest.path:
            tx._set_cancel()

        return request.redirect('/payment/status')
