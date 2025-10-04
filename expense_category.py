# type: ignore

from odoo import models, fields, api


class ExpenseCategory(models.Model):
    _name = 'expense.category'
    _description = 'Expense Category'
    _order = 'sequence, name'

    name = fields.Char(
        string='Category Name',
        required=True,
        translate=True
    )
    code = fields.Char(
        string='Code',
        required=True,
        size=10
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )
    requires_receipt = fields.Boolean(
        string='Requires Receipt',
        default=True,
        help='If checked, expenses in this category must have a receipt attached'
    )
    description = fields.Text(
        string='Description',
        translate=True
    )
    parent_id = fields.Many2one(
        'expense.category',
        string='Parent Category',
        ondelete='cascade'
    )
    child_ids = fields.One2many(
        'expense.category',
        'parent_id',
        string='Child Categories'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code, company_id)', 'Category code must be unique per company!'),
    ]

    @api.depends('name', 'code')
    def name_get(self):
        result = []
        for category in self:
            name = f"[{category.code}] {category.name}"
            result.append((category.id, name))
        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        if name:
            categories = self.search([
                '|', ('name', operator, name),
                ('code', operator, name)
            ] + args, limit=limit)
            return categories.name_get()
        return super().name_search(name, args, operator, limit)
