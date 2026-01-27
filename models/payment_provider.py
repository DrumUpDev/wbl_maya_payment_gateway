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


from odoo import models, fields
import base64
import logging 

logger = logging.getLogger(__name__)

class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('maya', "Maya")],
        required = True,
        string = "Code",
        ondelete={'maya': 'set default'}
    )

    maya_public_key = fields.Char("Public Key", groups='base.group_user')
    maya_secret_key = fields.Char("Maya Secret Key", groups='base.group_user')

    def _get_supported_features(self):
        supported = super()._get_supported_features()
        logger.info("supprted feature", supported)
        if self.provider_code == 'maya':
            supported.update({
                'redirect': True,
            })
        return supported

    def _process_feedback_data(self, data):
        """Process the callback result from Maya"""
        self.ensure_one()
        logger.info("Processing feedback", self.provider_code, data)
        if self.provider_code != 'maya':
            return super()._process_feedback_data(data)

        status = data.get('status')
        if status == 'PAYMENT_SUCCESS':
            self._set_transaction_done()
        elif status == 'PAYMENT_FAILED':
            self._set_transaction_cancel()
        else:
            self._set_transaction_pending()
            
            
            

    
    
    
    
