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
import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

MAYA_SANDBOX_URL = "https://pg-sandbox.paymaya.com"
MAYA_PRODUCTION_URL = "https://pg.paymaya.com"


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('maya', "Maya")],
        required=True,
        ondelete={'maya': 'set default'},
    )

    maya_public_key = fields.Char("Maya Public Key", groups='base.group_user')
    maya_secret_key = fields.Char("Maya API Secret Key", groups='base.group_user')
    maya_webhook_secret = fields.Char(
        "Maya Webhook Secret",
        groups='base.group_system',
        help="Shared secret used to verify webhook signatures."
    )
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

    @api.model
    def _maya_find_provider_for_webhook(self, headers, raw_body):
        """
        Find and verify the Maya provider for incoming webhook request.
        Accepted verifications:
          1) Authorization Basic with configured key
          2) X-Maya-Signature (HMAC SHA256) using webhook secret (fallback API secret)
        """
        providers = self.sudo().search([('code', '=', 'maya')])
        if not providers:
            return self.browse()

        authorization = (headers.get('Authorization') or '').strip()
        signature = (headers.get('X-Maya-Signature') or headers.get('x-maya-signature') or '').strip()

        for provider in providers:
            # 1) Basic Authorization match
            if authorization:
                tokens = []
                if provider.maya_public_key:
                    tokens.append("Basic " + base64.b64encode((provider.maya_public_key + ":").encode()).decode())
                if provider.maya_secret_key:
                    tokens.append("Basic " + base64.b64encode((provider.maya_secret_key + ":").encode()).decode())

                for token in tokens:
                    if hmac.compare_digest(authorization, token):
                        return provider

            # 2) Signature match (hex or base64)
            secret = provider.maya_webhook_secret or provider.maya_secret_key
            if signature and secret:
                digest = hmac.new(secret.encode(), raw_body, hashlib.sha256)
                expected_hex = digest.hexdigest()
                expected_b64 = base64.b64encode(digest.digest()).decode()

                if hmac.compare_digest(signature, expected_hex) or hmac.compare_digest(signature, expected_b64):
                    return provider

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
        tx = tx_model._maya_resolve_from_webhook_payload(data or {})
        if tx:
            scenario = tx_model._maya_extract_scenario(data or {})
            tx._maya_apply_webhook_scenario(scenario, data or {})
        return tx

            

    
    
    
    
