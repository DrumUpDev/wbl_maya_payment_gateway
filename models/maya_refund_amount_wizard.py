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

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class MayaRefundAmountWizard(models.TransientModel):
    _name = 'maya.refund.amount.wizard'
    _description = 'Maya Refund Amount Wizard'

    refund_amount = fields.Monetary(string="Refund Amount", required=True)
    currency_id = fields.Many2one('res.currency', string="Currency", required=True,
                                  default=lambda self: self.env.company.currency_id)
    transaction_parent_id = fields.Many2one('payment.transaction', string="Refund Parent Transaction", readonly=True,
                                            copy=False)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id:
            payment = self.env['account.payment'].browse(active_id)
            if payment.payment_transaction_id:
                # Get PHP currency record
                php_currency = self.env['res.currency'].search([('name', '=', 'PHP')], limit=1)

                res.update({
                    'refund_amount': payment.payment_transaction_id.amount,
                    'currency_id': php_currency.id if php_currency else payment.payment_transaction_id.currency_id.id,
                    'transaction_parent_id': payment.payment_transaction_id.id,
                })
        return res

    def confirm_refund(self):
        _logger.info("Maya Refund Wizard: confirm_refund called")
        active_id = self.env.context.get('active_id')
        if not active_id:
            raise ValidationError("Active transaction not found.")
        payment = self.env['account.payment'].browse(active_id)
        if not payment.payment_transaction_id:
            raise ValidationError("No linked Maya transaction found.")
        tx = payment.payment_transaction_id
        _logger.info("Processing refund on transaction ID %s", tx.id)
        tx.action_maya_refund(amount=self.refund_amount)
        return {'type': 'ir.actions.act_window_close'}
