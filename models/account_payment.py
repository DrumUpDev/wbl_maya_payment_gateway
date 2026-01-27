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

from odoo import models, api, fields
from odoo.exceptions import UserError
import json
import base64
import requests
import logging

logger = logging.getLogger(__name__)

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    maya_payment_type = fields.Selection([
        ('DB', 'Debit'),
        ('RF', 'Refund')
    ], string="Maya Payment Type", readonly=True)

    maya_show_refund = fields.Boolean(compute="_compute_maya_refund_visible", store=False)

    @api.depends('payment_method_line_id')
    def _compute_maya_refund_visible(self):
        for rec in self:
            rec.maya_show_refund = (
                    rec.payment_method_line_id
                    and rec.payment_method_line_id.payment_provider_id
                    and rec.payment_method_line_id.payment_provider_id.code == 'maya'
            )

    def action_open_refund_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Refund',
            'res_model': 'maya.refund.amount.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_refund_amount': self.amount,
                'default_currency_id': self.currency_id.id,
                'default_payment_id': self.id,
            }
        }