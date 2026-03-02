# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class MayaWebhookEvent(models.Model):
    _name = 'maya.webhook.event'
    _description = 'Maya Webhook Event'
    _order = 'id desc'

    event_key = fields.Char(required=True, index=True, readonly=True)
    provider_id = fields.Many2one(
        'payment.provider',
        required=True,
        readonly=True,
        index=True,
        ondelete='cascade',
    )
    transaction_id = fields.Many2one(
        'payment.transaction',
        readonly=True,
        index=True,
        ondelete='set null',
    )
    scenario = fields.Char(readonly=True, index=True)
    state = fields.Selection(
        [
            ('received', 'Received'),
            ('processed', 'Processed'),
            ('ignored', 'Ignored'),
            ('error', 'Error'),
        ],
        required=True,
        default='received',
        readonly=True,
        index=True,
    )
    payload = fields.Text(readonly=True)
    processing_message = fields.Char(readonly=True)

    _event_key_uniq = models.Constraint(
        'UNIQUE(provider_id, event_key)',
        'Webhook event already processed for this provider.',
    )

    @api.autovacuum
    def _gc_old_maya_webhook_events(self):
        """
        Keep table size controlled.
        """
        cutoff = fields.Datetime.now() - timedelta(days=90)
        old_records = self.search([('create_date', '<', cutoff)])
        if old_records:
            old_records.unlink()
        return True
