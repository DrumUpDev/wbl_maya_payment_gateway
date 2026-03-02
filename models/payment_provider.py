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
import hmac
import ipaddress
import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

MAYA_SANDBOX_URL = "https://pg-sandbox.paymaya.com"
MAYA_PRODUCTION_URL = "https://pg.paymaya.com"
MAYA_SANDBOX_WEBHOOK_IPS = frozenset([
    "13.229.160.234",
    "3.1.199.75",
])
MAYA_PRODUCTION_WEBHOOK_IPS = frozenset([
    "18.138.50.235",
    "3.1.207.200",
])


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('maya', "Maya")],
        required=True,
        ondelete={'maya': 'set default'},
    )

    maya_public_key = fields.Char("Maya Public Key", groups='base.group_user')
    maya_secret_key = fields.Char("Maya API Secret Key", groups='base.group_user')
    maya_api_timeout = fields.Integer(
        string="Maya API Timeout (seconds)",
        default=30,
        help="Timeout for Maya API requests."
    )

    @api.constrains('maya_api_timeout')
    def _check_maya_api_timeout(self):
        for rec in self:
            if rec.maya_api_timeout and rec.maya_api_timeout <= 0:
                raise ValidationError("Maya API timeout must be greater than 0.")

    def _get_supported_features(self):
        self.ensure_one()
        supported = super()._get_supported_features()
        if self.code == 'maya':
            supported.update({
                'redirect': True,
            })
        return supported

    def _maya_get_api_base_url(self):
        self.ensure_one()
        return MAYA_PRODUCTION_URL if self.state == 'enabled' else MAYA_SANDBOX_URL

    def _maya_get_allowed_webhook_ips(self):
        self.ensure_one()
        return MAYA_PRODUCTION_WEBHOOK_IPS if self.state == 'enabled' else MAYA_SANDBOX_WEBHOOK_IPS

    @staticmethod
    def _maya_normalize_signature(signature):
        """
        Accept common signature formats:
        - raw hex/base64
        - sha256=<value>
        - quoted values
        """
        normalized = (signature or '').strip()
        lower = normalized.lower()
        if lower.startswith('sha256='):
            normalized = normalized.split('=', 1)[1].strip()
        return normalized.strip('\'"')

    @staticmethod
    def _maya_normalize_ip(value):
        ip_value = (value or '').strip()
        if not ip_value:
            return ''

        # X-Forwarded-For can carry a chain; the first IP is the client.
        if ',' in ip_value:
            ip_value = ip_value.split(',', 1)[0].strip()

        if ip_value.lower().startswith('::ffff:'):
            ip_value = ip_value[7:]

        try:
            return str(ipaddress.ip_address(ip_value))
        except ValueError:
            return ''

    @api.model
    def _maya_extract_request_ip(self, headers, remote_addr=''):
        # Security hardening: do not trust forwarding headers for auth fallback.
        # Only the direct socket source IP can be used for allowlist verification.
        _ = headers
        return self._maya_normalize_ip(remote_addr)

    @api.model
    def _maya_find_provider_for_webhook(self, headers, raw_body, remote_addr=''):
        """
        Find and verify the Maya provider for incoming webhook request.
        Accepted verifications:
          1) Authorization Basic with configured key
          2) Maya/PayMaya signature header (HMAC SHA256) using API secret key
          3) Source IP allowlist fallback (per Maya docs)
        """
        providers = self.sudo().search([('code', '=', 'maya')])
        if not providers:
            return self.browse()

        authorization = (headers.get('Authorization') or headers.get('authorization') or '').strip()
        signature = ''
        signature_header = ''
        for header_name in (
            'X-Maya-Signature',
            'x-maya-signature',
            'X-PayMaya-Signature',
            'x-paymaya-signature',
            'PayMaya-Signature',
            'paymaya-signature',
        ):
            raw_signature = headers.get(header_name)
            if raw_signature:
                signature = raw_signature.strip()
                signature_header = header_name
                break

        auth_b64 = ''
        auth_scheme = ''
        if authorization:
            scheme, _, token = authorization.partition(' ')
            auth_scheme = (scheme or '').lower()
            if scheme.lower() == 'basic' and token:
                auth_b64 = token.strip()

        request_ip = self._maya_extract_request_ip(headers=headers, remote_addr=remote_addr)
        _logger.info(
            "Maya webhook auth debug: remote_addr=%s request_ip=%s providers=%s "
            "has_authorization=%s auth_scheme=%s has_signature=%s signature_header=%s signature_len=%s",
            remote_addr or '',
            request_ip or '',
            len(providers),
            bool(authorization),
            auth_scheme or '',
            bool(signature),
            signature_header or '',
            len(signature),
        )

        providers_with_basic_key = 0
        providers_with_signature_key = 0

        for provider in providers:
            # 1) Basic Authorization match
            if auth_b64:
                tokens = []
                public_key = (provider.maya_public_key or '').strip()
                secret_key = (provider.maya_secret_key or '').strip()
                if public_key or secret_key:
                    providers_with_basic_key += 1
                if public_key:
                    tokens.append(base64.b64encode((public_key + ":").encode()).decode())
                if secret_key:
                    tokens.append(base64.b64encode((secret_key + ":").encode()).decode())
                if public_key and secret_key:
                    tokens.append(base64.b64encode((public_key + ":" + secret_key).encode()).decode())

                for token in tokens:
                    if hmac.compare_digest(auth_b64, token):
                        _logger.info(
                            "Maya webhook auth debug: provider matched via basic auth provider_id=%s state=%s",
                            provider.id,
                            provider.state,
                        )
                        return provider

            # 2) Signature match (hex or base64)
            secret = (provider.maya_secret_key or '').strip()
            if secret:
                providers_with_signature_key += 1
            normalized_signature = self._maya_normalize_signature(signature)
            if normalized_signature and secret:
                digest = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256)
                expected_hex = digest.hexdigest()
                expected_b64 = base64.b64encode(digest.digest()).decode()

                if hmac.compare_digest(normalized_signature, expected_hex) or hmac.compare_digest(normalized_signature, expected_b64):
                    _logger.info(
                        "Maya webhook auth debug: provider matched via signature provider_id=%s state=%s signature_header=%s",
                        provider.id,
                        provider.state,
                        signature_header or '',
                    )
                    return provider

            # 3) Source IP allowlist fallback
            allowed_ips = provider._maya_get_allowed_webhook_ips()
            if request_ip and request_ip in allowed_ips:
                _logger.info(
                    "Maya webhook provider verified by source IP provider_id=%s state=%s ip=%s",
                    provider.id, provider.state, request_ip
                )
                return provider

        _logger.warning(
            "Maya webhook auth failed: remote_addr=%s request_ip=%s providers_checked=%s "
            "has_authorization=%s auth_scheme=%s has_signature=%s signature_header=%s signature_len=%s "
            "providers_with_basic_key=%s providers_with_signature_key=%s",
            remote_addr or '',
            request_ip or '',
            len(providers),
            bool(authorization),
            auth_scheme or '',
            bool(signature),
            signature_header or '',
            len(signature),
            providers_with_basic_key,
            providers_with_signature_key,
        )
        return self.browse()

    def _process_feedback_data(self, data):
        """
        Keep this safe and minimal.
        Webhook controller is the source of truth for Maya.
        """
        self.ensure_one()
        if self.code != 'maya':
            return super()._process_feedback_data(data)

        tx_model = self.env['payment.transaction'].sudo()
        tx = tx_model._maya_resolve_from_webhook_payload(data or {}, provider=self)
        if tx:
            scenario = tx_model._maya_extract_scenario(data or {})
            tx._maya_apply_webhook_scenario(scenario, data or {})
        return tx

            

    
    
    
    
