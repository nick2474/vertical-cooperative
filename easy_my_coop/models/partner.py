# -*- coding: utf-8 -*-
from openerp import api, fields, models, _
from datetime import date

class ResPartner(models.Model):
    _inherit = 'res.partner'

#     def _auto_init(self, cr, context=None):
#         """
#             Convert the column birthdate into date if it's not the case to avoid warning and data loss with orm conversion
#         """
#         cr.execute("select data_type from information_schema.columns where table_name = 'res_partner' and column_name= 'birthdate';")
#         res = cr.fetchone()
#         if not 'date' in res:
#             cr.execute("ALTER TABLE res_partner ALTER COLUMN birthdate TYPE date USING birthdate::date;")
#         
#         return super(ResPartner, self)._auto_init(cr, context=context)

    @api.multi
    def _invoice_total(self):
        account_invoice_report = self.env['account.invoice.report']
        if not self.ids:
            self.total_invoiced = 0.0
            return True
 
        user_currency_id = self.env.user.company_id.currency_id.id
        all_partners_and_children = {}
        all_partner_ids = []
        for partner in self:
            # price_total is in the company currency
            all_partners_and_children[partner] = self.search([('id', 'child_of', partner.id)]).ids
            all_partner_ids += all_partners_and_children[partner]
 
        # searching account.invoice.report via the orm is comparatively expensive
        # (generates queries "id in []" forcing to build the full table).
        # In simple cases where all invoices are in the same currency than the user's company
        # access directly these elements

        # generate where clause to include multicompany rules
        where_query = account_invoice_report._where_calc([
            ('partner_id', 'in', all_partner_ids), ('state', 'not in', ['draft', 'cancel']), ('company_id', '=', self.env.user.company_id.id),
            ('type', 'in', ('out_invoice', 'out_refund')),
            ('release_capital_request','=',False),
        ])
        account_invoice_report._apply_ir_rules(where_query, 'read')
        from_clause, where_clause, where_clause_params = where_query.get_sql()

        # price_total is in the company currency
        query = """
                  SELECT SUM(price_total) as total, partner_id
                    FROM account_invoice_report account_invoice_report
                   WHERE %s
                   GROUP BY partner_id
                """ % where_clause
        self.env.cr.execute(query, where_clause_params)
        price_totals = self.env.cr.dictfetchall()
        for partner, child_ids in all_partners_and_children.items():
            partner.total_invoiced = sum(price['total'] for price in price_totals if price['partner_id'] in child_ids)

    @api.multi
    def _get_share_type(self):
        share_type_list = [('','')]
        for share_type in self.env['product.product'].search([('is_share','=',True)]):
            share_type_list.append((str(share_type.id),share_type.short_name))
        return share_type_list

    @api.multi
    @api.depends('share_ids')
    def _compute_effective_date(self):
        #TODO change it to compute it from the share register
        for partner in self:
            if partner.share_ids:
                partner.effective_date = partner.share_ids[0].effective_date  
    
    @api.multi
    @api.depends('share_ids')
    def _compute_cooperator_type(self):
        for partner in self:
            share_type = ''
            for line in partner.share_ids:
                share_type = str(line.share_product_id.id)
            if share_type != '':
                partner.cooperator_type = share_type

    @api.multi
    @api.depends('share_ids')
    def _compute_share_info(self):
        for partner in self:
            number_of_share = 0
            total_value =  0.0
            for line in partner.share_ids:
                number_of_share += line.share_number
                total_value += line.share_unit_price * line.share_number
            partner.number_of_share = number_of_share
            partner.total_value = total_value
     
    cooperator = fields.Boolean(string='Cooperator', help="Check this box if this contact is a cooperator(effective or not).")
    member = fields.Boolean(string='Effective cooperator', help="Check this box if this cooperator is an effective member.")
    coop_candidate = fields.Boolean(string="Cooperator candidate", compute="_compute_coop_candidate", store=True, readonly=True)
    old_member = fields.Boolean(string='Old cooperator', help="Check this box if this cooperator is no more an effective member.")
    gender = fields.Selection([('male', 'Male'), ('female', 'Female'), ('other', 'Other')], string='Gender')
    national_register_number = fields.Char(string='National Register Number')
    share_ids = fields.One2many('share.line','partner_id',string='Share Lines')
    cooperator_register_number = fields.Integer(string='Cooperator Number')
    #birthdate = fields.Date(string="Birthdate")
    number_of_share = fields.Integer(compute="_compute_share_info", multi='share', string='Number of share', readonly=True)
    total_value = fields.Float(compute="_compute_share_info", multi='share', string='Total value of shares', readonly=True)
    company_register_number = fields.Char(string='Company Register Number')
    cooperator_type = fields.Selection(selection='_get_share_type', compute='_compute_cooperator_type', string='Cooperator Type', store=True)
    effective_date = fields.Date(sting="Effective Date", compute='_compute_effective_date', store=True)
    representative = fields.Boolean(string="Legal Representative")
    subscription_request_ids = fields.One2many('subscription.request', 'partner_id', string="Subscription request")
    
    @api.multi
    @api.depends('subscription_request_ids.state')
    def _compute_coop_candidate(self):
        for partner in self:
            paid_sub_req = partner.subscription_request_ids.filtered(lambda record: record.state == 'paid')
            if paid_sub_req:
                is_candidate = False
            else:
                if len(partner.subscription_request_ids.filtered(lambda record: record.state != 'cancelled')) > 0:
                    is_candidate = True
                else :
                    is_candidate = False
             
            partner.coop_candidate = is_candidate
            
    def has_representative(self):
        if self.child_ids.filtered('representative'):
            return True
        return False
    
    def get_representative(self):
        return self.child_ids.filtered('representative')

    def get_cooperator_from_nin(self, national_id_number):
        return self.search([('cooperator','=',True),('national_register_number','=',national_id_number)])
    
    def get_cooperator_from_crn(self, company_register_number):
        return self.search([('cooperator','=',True),('company_register_number','=',company_register_number)])