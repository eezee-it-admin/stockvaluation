# -*- coding: utf-8 -*-
# ############################################################################
#
#    Copyright Eezee-It (C) 2020
#    Author: Eezee-It <info@eezee-it.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from odoo import models
from odoo.tools import float_is_zero


class Product(models.Model):
    _inherit = 'product.product'

    def _prepare_out_svl_vals(self, quantity, company):
        if not self._context.get('lot_id'):
            return super(Product, self)._prepare_out_svl_vals(
                quantity, company
            )
        """Prepare the vals for a stock valuation layer created by a delivery.

        :param quantity: the quantity to value, expressed in `self.uom_id`
        :return: values to use in a call to create
        :rtype: dict
        """
        self.ensure_one()
        # Quantity is negative for out valuation layers.
        quantity = -1 * quantity
        vals = {
            'product_id': self.id,
            'value': quantity * self.standard_price,
            'unit_cost': self.standard_price,
            'quantity': quantity,
        }
        if self.cost_method in ('average', 'fifo'):
            # Get the cost values from the SVL filtered based on the Lot.
            fifo_vals = self._run_fifo(abs(quantity), company)
            vals['remaining_qty'] = fifo_vals.get('remaining_qty')
            vals.update(fifo_vals)
        return vals

    def _run_fifo(self, quantity, company):
        self.ensure_one()
        if not self._context.get('lot_id'):
            return super(Product, self)._run_fifo(quantity, company)
        qty_to_take_on_candidates = quantity
        svl_obj = self.env['stock.valuation.layer']
        candidates = svl_obj.sudo().with_context(active_test=False).search([
            ('product_id', '=', self.id),
            ('remaining_qty', '>', 0),
            ('lot_id', '=', self._context.get('lot_id').id),
            ('company_id', '=', company.id),
        ])
        new_standard_price = 0
        tmp_value = 0  # to accumulate the value taken on the candidates
        for candidate in candidates:
            qty_taken_on_candidate = min(
                qty_to_take_on_candidates,
                candidate.remaining_qty
            )

            unit_cost = candidate.remaining_value / candidate.remaining_qty
            new_standard_price = unit_cost
            value_taken_on_candidate = qty_taken_on_candidate * unit_cost
            value_taken_on_candidate = candidate.currency_id.round(
                value_taken_on_candidate
            )
            new_value = candidate.remaining_value - value_taken_on_candidate

            new_qty = candidate.remaining_qty - qty_taken_on_candidate
            candidate_vals = {
                'remaining_qty': new_qty,
                'remaining_value': new_value,
            }

            candidate.write(candidate_vals)

            qty_to_take_on_candidates -= qty_taken_on_candidate
            tmp_value += value_taken_on_candidate
            if float_is_zero(
                qty_to_take_on_candidates,
                precision_rounding=self.uom_id.rounding
            ):
                break

        if new_standard_price and self.cost_method == 'fifo':
            self.sudo().with_context(
                force_company=company.id
            ).standard_price = new_standard_price

        vals = {}
        if float_is_zero(
            qty_to_take_on_candidates,
            precision_rounding=self.uom_id.rounding
        ):
            vals = {
                'value': -tmp_value,
                'unit_cost': tmp_value / quantity,
            }
        else:
            assert qty_to_take_on_candidates > 0
            last_fifo_price = new_standard_price or self.standard_price
            negative_stock_value = last_fifo_price * -qty_to_take_on_candidates
            tmp_value += abs(negative_stock_value)
            vals = {
                'remaining_qty': -qty_to_take_on_candidates,
                'value': -tmp_value,
                'unit_cost': last_fifo_price,
            }
        return vals
