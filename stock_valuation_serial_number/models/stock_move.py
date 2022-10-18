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
from odoo import fields, models
from odoo.tools import float_is_zero


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _create_in_svl(self, forced_quantity=None):
        """Create a `stock.valuation.layer` from `self`.
        :param forced_quantity: under some circunstances,
            the quantity to value is different than
            the initial demand of the move (Default value = None)
        """
        svl_obj = self.env['stock.valuation.layer'].sudo()
        svls = svl_obj
        svl_vals_list = []
        sn_moves = self.filtered(lambda m: m.product_id.tracking == 'serial')
        normal_moves = self - sn_moves
        if normal_moves:
            svls |= super(StockMove, normal_moves)._create_in_svl(
                forced_quantity=forced_quantity
            )
        for move in sn_moves:
            move = move.with_context(force_company=move.company_id.id)
            valued_move_lines = move._get_in_move_lines()
            valued_quantity = 0
            for valued_move_line in valued_move_lines:
                valued_quantity =\
                    valued_move_line.product_uom_id._compute_quantity(
                        valued_move_line.qty_done, move.product_id.uom_id)
                # May be negative (i.e. decrease an out move)
                unit_cost = abs(move._get_price_unit())
                if move.product_id.cost_method == 'standard':
                    unit_cost = move.product_id.standard_price
                svl_vals = move.product_id._prepare_in_svl_vals(
                    forced_quantity or valued_quantity, unit_cost)
                svl_vals.update(move._prepare_common_svl_vals())
                # Add lot_id in SVL
                svl_vals.update({'lot_id': valued_move_line.lot_id.id})
                if forced_quantity:
                    desc = 'Correction of %s (modification of past move)'\
                        % move.picking_id.name or move.name
                    svl_vals['description'] = desc
                svl_vals_list.append(svl_vals)
        return svls + svl_obj.create(svl_vals_list)

    def _create_out_svl(self, forced_quantity=None):
        """Create a `stock.valuation.layer` from `self`.

        :param forced_quantity: under some circunstances, the quantity
        to value is different than
            the initial demand of the move (Default value = None)
        """
        svl_vals_list = []
        for move in self:
            move = move.with_context(force_company=move.company_id.id)
            valued_move_lines = move._get_out_move_lines()
            valued_quantity = 0
            for valued_move_line in valued_move_lines:
                valued_quantity =\
                    valued_move_line.product_uom_id._compute_quantity(
                        valued_move_line.qty_done, move.product_id.uom_id)
                if float_is_zero(
                    forced_quantity or valued_quantity,
                    precision_rounding=move.product_id.uom_id.rounding
                ):
                    continue
                svl_vals = move.product_id.with_context(
                    lot_id=valued_move_line.lot_id
                )._prepare_out_svl_vals(
                    forced_quantity or valued_quantity, move.company_id)
                svl_vals.update(move._prepare_common_svl_vals())
                if forced_quantity:
                    svl_vals['description'] =\
                        'Correction of %s (modification of past move)' %\
                        move.picking_id.name or move.name
                svl_vals_list.append(svl_vals)
        return self.env['stock.valuation.layer'].sudo().create(svl_vals_list)
