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

{
    'name': 'Maya Payment Gateway With Refund',
    'version': '19.0.1.0.0',
    'summary': """Maya odoo payment, Paymaya gateway, Philippines pay gateway, Maya pay connect, Maya payments, PayMaya easy pay, Odoo payment Philippines, Maya Payment gateway,  Secure pay Philippines, Maya payment with refund, Refund with Maya, PayMaya integration, Maya PayMaya integration, Maya payment API, secure peso payments, Maya payment portal, API payment integration Philippines, PHP payment gateway, Maya card payment, Maya payment acquirer, PayMaya payment acquirer, Paymaya payment with refund, Maya payment gateway with refund, Maya with refund.""",
    'description': """Maya odoo payment, Paymaya gateway, Philippines pay gateway, Maya pay connect, Maya payments, PayMaya easy pay, Odoo payment Philippines, Maya Payment gateway,  Secure pay Philippines, Maya payment with refund, Refund with Maya, PayMaya integration, Maya PayMaya integration, Maya payment API, secure peso payments, Maya payment portal, API payment integration Philippines, PHP payment gateway, Maya card payment, Maya payment acquirer, PayMaya payment acquirer, Paymaya payment with refund, Maya payment gateway with refund, Maya with refund.""",
    'category': 'Website',
    'author': 'Weblytic Labs',
    'company': 'Weblytic Labs',
    'website': 'https://store.weblyticlabs.com',
    'depends': ['base','payment','website','website_sale'],
    'price': '175.00',
    'currency': 'USD',
    'data': [
        'security/ir.model.access.csv',
        'views/payment_provider_views.xml',
        'views/payment_maya_templates.xml',
        'views/payment_transaction_views.xml',
        'views/maya_refund_wizard_view.xml',
        'views/refund_button.xml',

        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',
    ],
    'images': ['static/description/banner.gif'],
    'live_test_url': 'https://youtu.be/WxtLS_jEOmQ',
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
