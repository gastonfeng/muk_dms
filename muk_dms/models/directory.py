###################################################################################
# 
#    Copyright (C) 2017 MuK IT GmbH
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###################################################################################

import os
import json
import base64
import logging
import functools

from collections import defaultdict

from odoo import _, models, api, fields, tools
from odoo.modules.module import get_resource_path
from odoo.exceptions import ValidationError, AccessError

from odoo.addons.muk_utils.tools import file

_logger = logging.getLogger(__name__)

class Directory(models.Model):
    
    _name = 'muk_dms.directory'
    _description = "Directory"
    
    _inherit = [
        'muk_utils.mixins.hierarchy',
        'muk_security.mixins.access_rights',
        'muk_dms.mixins.thumbnail',
    ]
    
    _order = "name asc, write_date desc"

    _parent_store = True
    _parent_name = "parent_directory"
    
    _parent_path_sudo = False
    _parent_path_store = False

    #----------------------------------------------------------
    # Database
    #----------------------------------------------------------
    
    name = fields.Char(
        string="Name", 
        required=True,
        index=True)
   
    is_root_directory = fields.Boolean(
        string="Is Root Directory", 
        default=False,
        help="""Indicates if the directory is a root directory. A root directory has a settings object,
            while a directory with a set parent inherits the settings form its parent.""")
   
    root_storage = fields.Many2one(
        comodel_name='muk_dms.storage',  
        string="Root Storage",
        ondelete='restrict')
   
    storage = fields.Many2one(
        compute='_compute_storage',
        comodel_name='muk_dms.storage', 
        string="Storage",
        ondelete='restrict',
        auto_join=True,
        readonly=True,
        store=True)
    
    parent_directory = fields.Many2one(
        comodel_name='muk_dms.directory', 
        domain="[('permission_create', '=', True), ('id', '!=', active_id)]",
        context="{'dms_directory_show_path': True}",
        string="Parent Directory",
        ondelete='restrict',
        auto_join=True,
        index=True)
    
    child_directories = fields.One2many(
        comodel_name='muk_dms.directory', 
        inverse_name='parent_directory',
        string="Subdirectories",
        auto_join=False,
        copy=False)
    
    is_hidden = fields.Boolean(
        string="Storage is Hidden", 
        related="storage.is_hidden",
        readonly=True)

    company = fields.Many2one(
        related="storage.company",
        comodel_name='res.company',
        string='Company',
        readonly=True)
    
    color = fields.Integer(
        string="Color",
        default=0)
     
    tags = fields.Many2many(
        comodel_name='muk_dms.tag',
        relation='muk_dms_directory_tag_rel', 
        column1='did',
        column2='tid',
        string='Tags')
     
    category = fields.Many2one(
        comodel_name='muk_dms.category', 
        string="Category")
    
    user_stars = fields.Many2many(
        comodel_name='res.users',
        relation='muk_dms_directory_star_rel',
        column1='did',
        column2='uid',
        string='Stars')
     
    starred = fields.Boolean(
        compute='_compute_starred',
        inverse='_inverse_starred',
        search='_search_starred',
        string="Starred")
     
    files = fields.One2many(
        comodel_name='muk_dms.file', 
        inverse_name='directory',
        string="Files",
        auto_join=False,
        copy=False)

    count_directories = fields.Integer(
        compute='_compute_count_directories',
        string="Count Subdirectories")
     
    count_files = fields.Integer(
        compute='_compute_count_files',
        string="Count Files")
         
    count_elements = fields.Integer(
        compute='_compute_count_elements',
        string="Count Elements")
    
    count_total_directories = fields.Integer(
        compute='_compute_count_total_directories',
        string="Total Subdirectories")
     
    count_total_files = fields.Integer(
        compute='_compute_count_total_files',
        string="Total Files")
    
    count_total_elements = fields.Integer(
        compute='_compute_count_total_elements',
        string="Total Elements")
     
    size = fields.Integer(
        compute='_compute_size',
        string="Size")    
    
    #----------------------------------------------------------
    # Functions
    #----------------------------------------------------------
    
    @api.multi
    def toggle_starred(self):
        updates = defaultdict(set)
        for record in self:
            vals = {'starred': not record.starred}
            updates[tools.frozendict(vals)].add(record.id)
        with self.env.norecompute():
            for vals, ids in updates.items():
                self.browse(ids).write(dict(vals))
        self.recompute()
    #----------------------------------------------------------
    # Search
    #----------------------------------------------------------
     
    @api.model
    def _search_starred(self, operator, operand):
        if operator == '=' and operand:
            return [('user_stars', 'in', [self.env.uid])]
        return [('user_stars', 'not in', [self.env.uid])]
 
    #----------------------------------------------------------
    # Read 
    #----------------------------------------------------------
     
    @api.depends('root_storage', 'parent_directory')
    def _compute_storage(self):
        for record in self:
            if record.is_root_directory:
                record.storage = record.root_storage
            else:
                record.storage = record.parent_directory.storage
    
    @api.depends('user_stars')
    def _compute_starred(self):
        for record in self:
            record.starred = self.env.user in record.user_stars
            
    @api.depends('child_directories')
    def _compute_count_directories(self):
        for record in self:
            record.count_directories = len(record.child_directories)
    
    @api.depends('files')
    def _compute_count_files(self):
        for record in self:
            record.count_files = len(record.files)
                
    @api.depends('child_directories', 'files')
    def _compute_count_elements(self):
        for record in self:
            elements = record.count_files 
            elements += record.count_directories
            record.count_elements = elements
            
    @api.multi
    def _compute_count_total_directories(self):
        for record in self:
            count = self.search_count([
                ('id', 'child_of', record.id)
            ])
            record.count_total_directories = count - 1
            
    @api.multi
    def _compute_count_total_files(self):
        model = self.env['muk_dms.file']
        for record in self:
            record.count_total_files = model.search_count([
                ('directory', 'child_of', record.id)
            ])
    
    @api.multi
    def _compute_count_total_elements(self):
        for record in self:
            total_elements = record.count_total_files 
            total_elements += record.count_total_directories
            record.count_total_elements = total_elements
    
    @api.multi
    def _compute_size(self):
        sudo_model = self.env['muk_dms.file'].sudo()
        for record in self:
            recs = sudo_model.search_read(
                domain=[('directory', 'child_of', record.id)], 
                fields=['size'],
            )
            record.size = sum(rec.get('size', 0) for rec in recs)
    
    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        domain = list(args or [])
        if not (name == '' and operator == 'ilike') :
            if '/' in name:
                domain += [('parent_path_names', operator, name)]  
            else:
                domain += [(self._rec_name, operator, name)]
        records = self.browse(self._search(domain, limit=limit, access_rights_uid=name_get_uid))
        return models.lazy_name_get(records.sudo(name_get_uid or self.env.uid)) 
            
    @api.multi
    def name_get(self):
        if self.env.context.get('dms_directory_show_path'):
            res = []
            for record in self:
                names = record.parent_path_names
                if not names:
                    res.append(super(Directory, record).name_get()[0])
                elif not len(names) > 50:
                    res.append((record.id, names))
                else:
                    res.append((record.id, ".." + names[-48:]))
            return res
        return super(Directory, self).name_get()
        
    #----------------------------------------------------------
    # View
    #----------------------------------------------------------
    
    @api.onchange('is_root_directory') 
    def _onchange_directory_type(self):
        if self.is_root_directory:
            self.parent_directory = None
        else:
            self.root_storage = None
    
    #----------------------------------------------------------
    # Constrains
    #----------------------------------------------------------
    
    @api.constrains('parent_directory')
    def _check_directory_recursion(self):
        if not self._check_recursion():
            raise ValidationError(_('Error! You cannot create recursive directories.'))
        return True
  
    @api.constrains('is_root_directory', 'root_storage', 'parent_directory')
    def _check_directory_storage(self):
        for record in self:
            if record.is_root_directory and not record.root_storage:
                raise ValidationError(_("A root directory has to have a root storage."))
            if not record.is_root_directory and not record.parent_directory:
                raise ValidationError(_("A directory has to have a parent directory."))
            if record.parent_directory and (record.is_root_directory or record.root_storage):
                raise ValidationError(_("A directory can't be a root and have a parent directory."))
     
    @api.constrains('parent_directory')
    def _check_directory_access(self):
        for record in self:
            if not record.parent_directory.check_access('create', raise_exception=False):
                raise ValidationError(_("The parent directory has to have the permission to create directories."))
     
    @api.constrains('name')
    def _check_name(self):
        for record in self:
            if not file.check_name(record.name):
                raise ValidationError(_("The directory name is invalid."))
            if record.is_root_directory:
                childs = record.sudo().root_storage.root_directories.name_get()
            else:
                childs = record.sudo().parent_directory.child_directories.name_get()
            if list(filter(lambda child: child[1] == record.name and child[0] != record.id, childs)):
                raise ValidationError(_("A directory with the same name already exists."))
     
    #----------------------------------------------------------
    # Create, Update, Delete
    #----------------------------------------------------------
     
    @api.multi
    def _inverse_starred(self):
        starred_records = self.env['muk_dms.directory'].sudo()
        not_starred_records = self.env['muk_dms.directory'].sudo()
        for record in self:
            if not record.starred and self.env.user in record.user_stars:
                starred_records |= record
            elif record.starred and self.env.user not in record.user_stars:
                not_starred_records |= record
        not_starred_records.write({'user_stars': [(4, self.env.uid)]})
        starred_records.write({'user_stars': [(3, self.env.uid)]})
        
    @api.multi
    @api.returns('self', lambda value: value.id)
    def copy(self, default=None):
        self.ensure_one()
        default = dict(default or [])
        names = []
        if 'root_storage' in default:
            storage = self.env['muk_dms.storage'].browse(default['root_storage'])
            names = storage.sudo().root_directories.mapped('name')
        elif 'parent_directory' in default:
            parent_directory = self.browse(default['parent_directory'])
            names = parent_directory.sudo().child_directories.mapped('name')
        elif self.is_root_directory:
            names = self.sudo().root_storage.root_directories.mapped('name')
        else:
            names = self.sudo().parent_directory.child_directories.mapped('name')
        default.update({'name': file.unique_name(self.name, names)})
        new = super(Directory, self).copy(default)
        for record in self.files:
            record.copy({'directory': new.id})
        for record in self.child_directories:
            record.copy({'parent_directory': new.id})
        return new

    @api.multi
    def write(self, vals):
        res = super(Directory, self).write(vals)
        if any(field in vals for field in ['root_storage', 'parent_directory']):
            records = self.sudo().search([('id', 'child_of', self.ids)]) - self
            if 'root_storage' in vals:
                records.write({'storage': vals['root_storage']})
            elif 'parent_directory' in vals:
                parent = self.browse([vals['parent_directory']])
                data = next(iter(parent.sudo().read(['storage'])), {})
                records.write({'storage': self._convert_to_write(data).get('storage')})
        return res

    @api.multi
    def unlink(self):
        self.check_access('unlink', raise_exception=True)
        domain = [
            '&', ('directory', 'child_of', self.ids), 
            '&', ('locked_by', '!=', self.env.uid),
            ('locked_by', '!=', False),
        ]
        if self.env['muk_dms.file'].sudo().search(domain):
            raise AccessError(_("A file is locked, the folder cannot be deleted.")) 
        self.env['muk_dms.file'].sudo().search([('directory', 'child_of', self.ids)]).unlink()
        return super(Directory, self.sudo().search([('id', 'child_of', self.ids)])).unlink()
