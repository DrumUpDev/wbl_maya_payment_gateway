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

import base64
import json
import requests
from odoo import models
import logging

from odoo.exceptions import UserError

logger = logging.getLogger(__name__)
from odoo import models, fields

# This is payment transaction models. it will work on paynow time
class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    maya_transaction_id = fields.Char(string="Maya Transaction ID")
    maya_currency = fields.Char(string="Maya Transaction Currency")
    maya_status = fields.Char(string="Maya Transaction Status")


    # It's a refund related field
    maya_refund_id = fields.Char(string="Maya Refund ID", readonly=True)
    maya_refund_currency = fields.Char(string="Maya Refund Currency", readonly=True)
    maya_refund_status = fields.Char(string="Maya Refund Status", readonly=True)

    def _get_specific_rendering_values(self, processing_values):
        logger.info("_get_specific_rendering_values: %s", processing_values)
        self.ensure_one()
        if self.provider_code != 'maya':
            return super()._get_specific_rendering_values(processing_values)

        base_url = self.provider_id.get_base_url()
        redirect_url = f"{base_url}/payment/maya/redirect?tx_id={self.id}"
        logger.info("redirect_url: %s", redirect_url)
        return {
            'tx': self,
            'tx_url': f"/payment/maya/redirect?tx_id={self.id}",
        }

    def action_maya_refund(self, amount):
        self.ensure_one()

        if self.provider_id.code != 'maya':
            raise UserError("Not a Maya transaction.")

        if not self.maya_transaction_id or not self.provider_reference:
            raise UserError("Missing Maya transaction or reference ID.")

        # Choose the correct base URL based on provider config
        is_sandbox = self.provider_id.state != "enabled"
        base_url = "https://pg-sandbox.paymaya.com" if is_sandbox else "https://pg.paymaya.com"
        url = f"{base_url}/p3/refund"

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Basic " + base64.b64encode((self.provider_id.maya_secret_key + ":").encode()).decode(),
            "Request-Reference-No": self.maya_transaction_id,
        }

        payload = {
            "paymentTransactionReferenceNo": self.provider_reference,
            "merchant": {
                "metadata": {
                    "refNo": self.reference
                }
            },
            "amount": {
                "currency": "PHP",
                "value": float(amount)
            },
            "reason": "Customer requested refund",
        }

        logger.info("Maya Refund Request Payload: %s", payload)

        response = requests.post(url, headers=headers, data=json.dumps(payload))
        logger.info(f"Maya refund response {response.status_code} {response.text}")

        if response.status_code not in (200, 201):
            raise UserError(f"Refund failed: {response.text}", )

        result = response.json()

        logger.info(f"Refund Result: {result}")

        # # Optional: store refund status and ID
        # self.write({
        #     'maya_refund_id': result.get("refundId"),
        #     'state': 'refunded',
        # })
        # Maya response
        result = response.json()

        self.write({
            "maya_refund_id": result.get("refundId"),
            "maya_refund_status": result.get("status") or result.get("refundStatus") or "requested",
            "maya_refund_currency": (result.get("amount") or {}).get("currency") or "PHP",
        })


        return True