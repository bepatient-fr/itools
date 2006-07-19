# -*- coding: ISO-8859-1 -*-
# Copyright (C) 2003-2005 Juan David Ib��ez Palomar <jdavid@itaapy.com>
#                    2005 Alexandre Fernandez <alex@itaapy.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

# Import from the Standard Library
import marshal
import urllib
import zlib

# Import from itools
from itools.datatypes import FileName
from itools import vfs
from itools.handlers.Folder import Folder as BaseFolder
##from itools.handlers.registry import build_handler
from itools.handlers.Text import Text
from itools import i18n
from itools import uri
from itools.stl import stl
from itools.web import get_context

# Import from itools.cms
import File
from Handler import Handler
from binary import Image
from handlers import Lock, Metadata
from LocaleAware import LocaleAware
from versioning import VersioningAware
from workflow import WorkflowAware
from utils import checkid, reduce_string
from widgets import Breadcrumb, Table
from registry import register_object_class, get_object_class



class Folder(Handler, BaseFolder):

    #########################################################################
    # Class metadata
    #########################################################################
    class_id = 'folder'
    class_version = '20040625'
    class_title = u'Folder'
    class_description = u'Organize your files and documents with folders.'
    class_icon16 = 'images/Folder16.png'
    class_icon48 = 'images/Folder48.png'
    class_views = [['browse_thumbnails', 'browse_list', 'browse_image'],
                   ['new_resource_form'],
                   ['edit_metadata_form']]


    search_criteria =  [
        {'id': 'title', 'title': u"Title"},
        {'id': 'text', 'title': u"Text"},
        {'id': 'name', 'title': u"Name"},
    ]


    #########################################################################
    # Aggregation relationship (what a generic folder can contain)
    class_document_types = []

    __fixed_handlers__ = []


    @classmethod
    def register_document_type(cls, handler_class):
        cls.class_document_types.append(handler_class)


    def get_document_types(self):
        return self.class_document_types


    @classmethod
    def new_instance_form(cls):
        namespace = {'class_id': cls.class_id,
                     'class_title': cls.gettext(cls.class_title)}

        root = get_context().root
        handler = root.get_handler('ui/Folder_new_instance.xml')
        return stl(handler, namespace)


    #######################################################################
    # Traverse
    #######################################################################
    GET__access__ = True
    def GET(self, context):
        # Try index
        for name in ['index.xhtml', 'index.html']:
            if self.has_handler(name):
                return context.uri.resolve2(name)

        return Handler.GET(self, context)


    def _get_handler(self, segment, uri):
        name = segment.name
        # Metadata
        if name.endswith('.metadata'):
            return Metadata(uri)
        if name.endswith('.lock'):
            return Lock(uri)
        # Get the format
        if self.has_handler('%s.metadata' % name):
            metadata = self.get_handler('%s.metadata' % name)
            format = metadata.get_property('format')
        else:
            format = vfs.get_mimetype(uri)

        cls = get_object_class(format)
        return cls(uri)


    def _get_handler_names(self):
        names = BaseFolder._get_handler_names(self)
        for name in names:
            if not name.startswith('.'):
                name, type, language = FileName.decode(name)
                if language is not None:
                    name = FileName.encode((name, type, None))
                    names.append(name)

        return names


    def _get_virtual_handler(self, segment):
        name = segment.name

        languages = [ x.split('.')[-1] for x in vfs.get_names(self.uri)
                      if x.startswith(name) ]
        languages = [ x for x in languages if x in i18n.languages ]

        if languages:
            # Get the best variant
            context = get_context()

            if context is None:
                language = None
            else:
                request = context.request
                language = request.accept_language.select_language(languages)

            # By default use whatever variant
            # (XXX we need a way to define the default)
            if language is None:
                language = languages[0]
            return self.get_handler('%s.%s' % (name, language))

        return BaseFolder._get_virtual_handler(self, segment)


    def before_set_handler(self, segment, handler, format=None, id=None,
                           move=False, **kw):
        name = segment.name
        if name.startswith('.'):
            return

        # Set metadata
        metadata = handler.get_metadata()
        if metadata is None:
            metadata = self.build_metadata(handler, format=format, **kw)
        self.set_handler('%s.metadata' % name, metadata)


    def after_set_handler(self, segment, handler, format=None, id=None,
                          move=False, **kw):
        from root import Root

        name = segment.name
        if name.startswith('.'):
            return

        root = self.get_root()
        if isinstance(root, Root):
            # Index
            handler = self.get_handler(segment)
            if isinstance(handler, Folder):
                for x, context in handler.traverse2():
                    if x.real_handler is not None:
                        context.skip = True
                    else:
                        if not x.name.startswith('.'):
                            root.index_handler(x)
            else:
                root.index_handler(handler)
            # Store history
            if move is False:
                if isinstance(handler, Folder):
                    for x in handler.traverse():
                        if isinstance(x, VersioningAware):
                            x.commit_revision()
                    else:
                        if isinstance(handler, VersioningAware):
                            handler.commit_revision()


    def on_del_handler(self, segment):
        from root import Root

        name = segment.name
        if not name.startswith('.'):
            handler = self.get_handler(segment)
            # Unindex
            root = self.get_root()
            if isinstance(root, Root):
                if isinstance(handler, Folder):
                    for x, context in handler.traverse2():
                        if x.real_handler is None:
                            root.unindex_handler(x)
                        else:
                            context.skip = True
                else:
                    root.unindex_handler(handler)
            # Keep database consistency
            if isinstance(handler, LocaleAware):
                handler.remove_translation()

            # Remove metadata
            self.del_handler('%s.metadata' % name)


    def build_metadata(self, handler, owner=None, format=None, **kw):
        """Return a Metadata object with sensible default values."""
        if owner is None:
            owner = ''
            context = get_context()
            if context is not None:
                if context.user is not None:
                    owner = context.user.name

        if format is None:
            format = handler.class_id

        if isinstance(handler, WorkflowAware):
            kw['state'] = handler.workflow.initstate

##      if not isinstance(handler, LocaleAware):
##          kw['dc:language'] = None

        return Metadata(handler_class=handler.__class__, owner=owner,
                        format=format, **kw)


    #######################################################################
    # API
    #######################################################################
    def search_handlers(self, path='.', format=None, state=None,
                        handler_class=None):
        container = self.get_handler(path)

        for name in container.get_handler_names():
            # Skip hidden handlers
            if name.startswith('.'):
                continue

            filename, type, language = FileName.decode(name)
            if language is not None:
                continue

            handler = container.get_handler(name)
            if isinstance(handler, LocaleAware):
                if not handler.is_master():
                    continue

            if handler_class is not None:
                if not isinstance(handler, handler_class):
                    continue

            get_property = getattr(handler, 'get_property', lambda x: None)
            if format is None or get_property('format') == format:
                if state is None:
                    yield handler
                else:
                    handler_state = get_property('state')
                    if handler_state == state:
                        yield handler


    #######################################################################
    # User interface
    #######################################################################
    def get_browse_view(self):
        context = get_context()
        options = {
            'thumb': 'browse_thumbnails',
            'list': 'browse_list',
            'image_gallery': 'browse_image',
        }
        key = context.get_cookie('browse')
        return options.get(key, 'browse_thumbnails')


    def get_firstview(self):
        """
        Returns the first allowed object view url, or None if there aren't.
        """
        user = get_context().user
        ac = self.get_access_control()

        for name in self.get_views():
            if ac.is_access_allowed(user, self, name):
                if name in ['browse_thumbnails', 'browse_list']:
                    name = self.get_browse_view()
                return name
        return None

    firstview = property(get_firstview, None, None, "")


    #######################################################################
    # Browse
    def _browse_namespace(self, line, object):
        pass


    def browse_namespace(self, icon_size, sortby='title_or_name',
                sortorder='up', batchstart='0', batchsize='20', query={},
                results=None):
        context = get_context()
        request = context.request

        root = context.root
        path_to_root = context.path.get_pathtoroot()
        search_subfolders = False

        # hack for search in a tree, search_subfolder is a path string
        search_subfolders = query.get('search_subfolders')

        if search_subfolders is not None:
            del query['search_subfolders']
        else:
            query['parent_path'] = self.get_abspath()

        if results is None:
            results = self.search(**query)

        # if search in subfolders is active we filter on path
        if search_subfolders is not None:
            abspath = self.get_abspath()
            results = [ x for x in results
                        if x.parent_path.startswith(abspath) ]

        # put the metadatas in a dictionary list to be managed with Table
        fields = root.get_catalog_metadata_fields()
        table_content = []
        for result in results:
            line = {}
            for field in fields:
                # put a '' if the brain doesn't have the given field
                line[field] = getattr(result, field, '')
            table_content.append(line)

        # Build the table
        tablename = 'content'
        table = Table(path_to_root, tablename, table_content, sortby=sortby,
                      sortorder=sortorder, batchstart=batchstart,
                      batchsize=batchsize)

        # Get the handler for the visibles documents and extracts values
        user = context.user
        objects = []
        for line in table.objects:
            abspath = line['abspath']
            document = root.get_handler(abspath)
            ac = document.get_access_control()
            if ac.is_allowed_to_view(user, document):
                uri = document.uri
                line = {}
                name = document.name
                line['abspath'] = abspath
                line['title_or_name'] = document.title_or_name
                line['name'] = str(self.get_pathto(document))
                line['format'] = document.get_property('format')
                line['class_title'] = self.gettext(document.class_title)
                line['title'] = document.get_property('dc:title')
                line['description'] = document.get_property('dc:description')
                line['is_file'] = vfs.is_file(uri)
                line['is_folder'] = vfs.is_folder(uri)
                line['ctime'] = vfs.get_ctime(uri)
                line['mtime'] = vfs.get_mtime(uri)
                line['atime'] = vfs.get_atime(uri)

                # compute size
                line['size'] = document.get_human_size()
                line['url'] = '%s/;%s' % (line['name'],
                                          document.get_firstview())
                path_to_icon = document.get_path_to_icon(icon_size,
                                                         from_handler=self)
                if path_to_icon.startswith(';'):
                    path_to_icon = uri.Path('%s/' % name).resolve(path_to_icon)
                line['icon'] = path_to_icon
                line['short_title'] = reduce_string(document.title_or_name,
                                                    12, 40)
                if 'language' in line.keys():
                    language = line['language']
                    if language:
                        language_name = i18n.get_language_name(language)
                        line['language'] = self.gettext(language_name)
                else:
                    line['language'] = ''
                line['mtime'] = document.mtime.strftime('%Y-%m-%d %H:%M')

                line['workflow_state'] = ''
                if isinstance(document, WorkflowAware):
                    state = document.get_state()
                    line['workflow_state'] = self.gettext(state['title'])

                # Document details
                line['details'] = '%s-details' % name
                is_image = isinstance(document, Image)
                line['is_image'] = is_image
                if is_image:
                    line['image_preview'] = '%s/;icon48?width=200&height=160' % name
                line['onclick'] = "hide_details('%s-details')" % name
                # Objects that should not be removed/renamed/etc
                line['checkbox'] = name not in self.__fixed_handlers__
                #
                self._browse_namespace(line, document)
                objects.append(line)
                
        table.objects = objects

        # Build namespace
        namespace = {}
        namespace['table'] = table
        namespace['batch'] = table.batch_control()
        # Paste?
        cp = context.get_cookie('ikaaro_cp')
        namespace['paste'] = cp is not None

        return namespace


    browse_thumbnails__access__ = 'is_authenticated'
    browse_thumbnails__label__ = u'Contents'
    browse_thumbnails__sublabel__ = u'As Icons'
    def browse_thumbnails(self, context):
        context.set_cookie('browse', 'thumb')

        parent_path = self.get_abspath()
        if parent_path in ('', None):
            parent_path = '/'
        query = {'parent_path' : parent_path}
        namespace = self.browse_namespace(48, query=query)

        handler = self.get_handler('/ui/Folder_browse_thumbnails.xml')
        return stl(handler, namespace)


    browse_list__access__ = 'is_allowed_to_edit'
    browse_list__label__ = u'Contents'
    browse_list__sublabel__ = u'As List'
    def browse_list(self, context):
        context = get_context()
        request = context.request

        context.set_cookie('browse', 'list')

        if context.has_form_value('search_value'):
            search_value = context.get_form_value('search_value')
            search_value = unicode(search_value, 'utf8').strip()
        else:
            search_value = u''

        search_subfolders = context.get_form_value('search_subfolders')
        if search_subfolders and not search_value:
            return context.come_back(
                u'Please put a value for your search criteria if you'
                u' include subfolders.')

        selected_criteria = context.get_form_value('search_criteria')

        query = {}
        if search_value:
            query[selected_criteria] = search_value
        if search_subfolders is not None:
            query['search_subfolders'] = search_subfolders

        namespace = self.browse_namespace(16, query=query)

        namespace['search_value'] = search_value
        namespace['search_subfolders'] = search_subfolders
        namespace['self_path'] = self.get_abspath()

        search_criteria = [
            {'id': x['id'],
             'title': self.gettext(x['title']),
             'selected': x['id'] == selected_criteria or None}
            for x in self.get_search_criteria() ]
        namespace['search_criteria'] = search_criteria

        handler = self.get_handler('/ui/Folder_browse_list.xml')
        return stl(handler, namespace)


    browse_image__access__ = 'is_allowed_to_edit'
    browse_image__label__ = u'Contents'
    browse_image__sublabel__ = u'As Image Gallery'
    def browse_image(self, context):
        selected_image = context.get_form_value('selected_image')
        selected_index = None

        # check selected image
        if selected_image is not None:
            path = uri.Path(selected_image)
            selected_image = path[-1].name
            if not selected_image in self.get_handler_names():
                selected_image = None

        # look up available images
        namespace = self.browse_namespace(48, batchsize='0')
        table = namespace['table']
        objects = []
        offset = 0
        for index, object in enumerate(table.objects):
            name = object['name']
            handler = self.get_handler(name)
            if not isinstance(handler, Image):
                offset = offset + 1
                continue
            if selected_image is None:
                selected_image = name
            if selected_image == name:
                selected_index = index - offset
            object['url'] = '?selected_image=%s' % name
            object['icon'] = '%s/;icon48?height=128&width=128' % name
            is_landscape = handler.get_width() >= handler.get_height()
            object['class'] = 'gallery_image %s' % (is_landscape and
                    'landscape' or 'portrait')
            objects.append(object)

        table.objects = objects

        # selected image namespace
        if selected_image is None:
            namespace['selected'] = None
        else:
            image = self.get_handler(selected_image)
            selected = {}
            selected['title_or_name'] = image.title_or_name
            selected['description'] = image.get_property('dc:description')
            selected['url'] = '%s/;%s' % (image.name, image.get_firstview())
            selected['preview'] = '%s/;icon48?height=320&width=320' \
                                  % image.name
            selected['width'] = image.get_width()
            selected['height'] = image.get_height()
            selected['format'] = image.get_format()
            if selected_index == 0:
                selected['previous'] = None
            else:
                previous = objects[selected_index - 1]['name']
                selected['previous'] = ';%s?selected_image=%s' % (
                        context.method, previous)
            if selected_index == (len(objects) - 1):
                selected['next'] = None
            else:
                next = objects[selected_index + 1]['name']
                selected['next'] = ';%s?selected_image=%s' % (context.method,
                        next)
            namespace['selected'] = selected

        handler = self.get_handler('/ui/Folder_browse_image.xml')
        return stl(handler, namespace)


    remove__access__ = 'is_allowed_to_remove'
    def remove(self, context):
        ids = context.get_form_values('ids')
        if not ids:
            return context.come_back(u'No objects selected.')

        removed = []
        not_allowed = []

        user = context.user
        for name in ids:
            handler = self.get_handler(name)
            ac = handler.get_access_control()
            if ac.is_allowed_to_remove(user, object):
                # Remove handler
                self.del_handler(name)
                removed.append(name)
            else:
                not_allowed.append(name)

        return context.come_back(
            u'Objects removed: $objects.', objects=', '.join(removed))


    rename_form__access__ = 'is_allowed_to_move'
    def rename_form(self, context):
        ids = context.get_form_values('ids')
        # Filter names which the authenticated user is not allowed to move
        handlers = [ self.get_handler(x) for x in ids ]
        names = [ x.name for x in handlers if x.is_allowed_to_move() ]

        # Check input data
        if not names:
            return context.come_back(u'No objects selected.')

        # XXX Hack to get rename working. The current user interface
        # forces the rename_form to be called as a form action, hence
        # with the POST method, but it should be a GET method. Maybe
        # it will be solved after the needed folder browse overhaul.
        if context.request.method == 'POST':
            ids_list = '&'.join([ 'ids=%s' % x for x in names ])
            return uri.get_reference(';rename_form?%s' % ids_list)

        # Build the namespace
        namespace = {}
        namespace['objects'] = []
        for real_name in names:
            name, extension, language = FileName.decode(real_name)
            namespace['objects'].append({'real_name': real_name, 'name': name})

        # Process the template
        handler = self.get_handler('/ui/Folder_rename.xml')
        return stl(handler, namespace)


    rename__access__ = 'is_allowed_to_move'
    def rename(self, context):
        names = context.get_form_value('names')
        new_names = context.get_form_value('new_names')
        # Process input data
        for i, old_name in enumerate(names):
            xxx, extension, language = FileName.decode(old_name)
            new_name = FileName.encode((new_names[i], extension, language))
            new_name = checkid(new_name)
            if new_name is None:
                # Invalid name
                return context.come_back(
                    u'The document name contains illegal characters,'
                    u' choose another one.')
            # Rename
            if new_name != old_name:
                handler = self.get_handler(old_name)
                handler_metadata = handler.get_metadata()

                if isinstance(handler, LocaleAware):
                    is_master = handler.is_master()
                    if not is_master:
                        master = handler.get_master_handler()

                # XXX itools should provide an API to copy and move handlers
                self.set_handler(new_name, handler, move=True)
                self.del_handler('%s.metadata' % new_name)
                self.set_handler('%s.metadata' % new_name, handler_metadata)
                self.del_handler(old_name)

        goto = uri.get_reference(';%s' % self.get_browse_view())
        message = self.gettext(u'Objects renamed.')
        return goto.replace(message=message)


    copy__access__ = 'is_allowed_to_copy'
    def copy(self, context):
        ids = context.get_form_values('ids')
        # Filter names which the authenticated user is not allowed to copy
        handlers = [ self.get_handler(x) for x in ids ]
        names = [ x.name for x in handlers if x.is_allowed_to_copy() ]

        if not names:
            return context.come_back(u'No objects selected.')

        path = self.get_abspath()
        cp = (False, [ '%s/%s' % (path, x) for x in names ])
        cp = urllib.quote(zlib.compress(marshal.dumps(cp), 9))
        context.set_cookie('ikaaro_cp', cp, path='/')

        return context.come_back(u'Objects copied.')


    cut__access__ = 'is_allowed_to_move'
    def cut(self, context):
        ids = context.get_form_values('ids')
        # Filter names which the authenticated user is not allowed to move
        handlers = [ self.get_handler(x) for x in ids ]
        names = [ x.name for x in handlers if x.is_allowed_to_move() ]

        if not names:
            return context.come_back(u'No objects selected.')

        path = self.get_abspath()
        cp = (True, [ '%s/%s' % (path, x) for x in names ])
        cp = urllib.quote(zlib.compress(marshal.dumps(cp), 9))
        context.set_cookie('ikaaro_cp', cp, path='/')

        return context.come_back(u'Objects cut.')


    paste__access__ = 'is_allowed_to_add'
    def paste(self, context):
        cp = context.get_cookie('ikaaro_cp')
        if cp is not None:
            root = context.root
            allowed_types = tuple(self.get_document_types())
            cut, paths = marshal.loads(zlib.decompress(urllib.unquote(cp)))
            for path in paths:
                handler = root.get_handler(path)
                if isinstance(handler, allowed_types):
                    name = handler.name
                    # Find a non used name
                    # XXX ROBLES To be tested carefully and optimized
                    while self.has_handler(name):
                        name = name.split('.')
                        id = name[0].split('_')
                        index = id[-1]
                        try:   # tests if id ends with a number
                            index = int(index)
                        except ValueError:
                            id.append('copy_1')
                        else:
                            try:  # tests if the pattern is '_copy_x'
                               if id[-2] == 'copy':
                                  index = str(index + 1) # increment index
                                  id[-1] = index
                               else:
                                  id.append('copy_1')
                            except IndexError:
                               id.append('copy_1')
                            else:
                               pass
                        id = '_'.join(id)
                        name[0] = id
                        name = '.'.join(name)
                    # Unicode is not a valid Zope id
                    name = str(name)
                    # Add it here
                    if cut is True:
                        self.set_handler(name, handler, move=True)
                        # Remove original
                        container = handler.parent
                        container.del_handler(name)
                    else:
                        self.set_handler(name, handler)
                        # Fix metadata properties
                        handler = self.get_handler(name)
                        metadata = handler.metadata
                        # Fix state
                        if isinstance(handler, WorkflowAware):
                            metadata.set_property('state', handler.workflow.initstate)
                        # Fix owner
                        metadata.set_property('owner', context.user.name)

        return context.come_back(u'Objects pasted.')


    #######################################################################
    # Browse / Translate
    translate_form__access__ = 'is_allowed_to_translate'
    def translate_form(self, context):
        context.get_form_values('ids')
        if not ids:
            raise UserError, self.gettext(u'No objects selected')

        # Check input data
        site_root = self.get_site_root()
        content_languages = site_root.get_property('ikaaro:website_languages')
        handlers = [ self.get_handler(x) for x in ids ]
        handlers = [ x for x in handlers if isinstance(x, LocaleAware) ]
        handlers = [ x for x in handlers if x.is_allowed_to_translate() ]
        handlers = [ x for x in handlers
                     if [ y for y in content_languages
                          if y not in x.get_available_languages() ] ]
        names = [ x.name for x in handlers ]

        if not names:
            message = u'The selected objects can not be translated.'
            raise UserError, self.gettext(message)

        # XXX Hack to get translate working. The current user interface
        # forces the translate_form to be called as a form action, hence
        # with the POST method, but is should be a GET method. Maybe
        # it will be solved after the needed folder browse overhaul.
        if context.request.method == 'POST':
            ids_list =  '&'.join([ 'ids:list=%s' % x for x in names ])
            context.redirect(';translate_form?%s' % ids_list)

        # Build the namespace
        namespace = {}
        # Documents
        documents = []
        for handler in handlers:
            document = {'name': handler.name,
                        'title_or_name': handler.title_or_name}
            languages = [ x for x in content_languages
                          if x not in handler.get_available_languages() ]
            document['languages'] = [
                {'code': x,
                 'name': self.gettext(i18n.get_language_name(x))}
                for x in languages ]
            documents.append(document)
        namespace['documents'] = documents

        # Process the template
        handler = self.get_handler('/ui/Folder_translate.xml')
        return stl(handler, namespace)


    translate__access__ = 'is_allowed_to_translate'
    def translate(self, context):
        names = context.get_form_value('names')
        languages = context.get_form_value('languages')

        for i in range(len(names)):
            name, type, language = FileName.decode(names[i])
            language = languages[i]
            trans_name = FileName.encode((name, type, language))
            name = names[i]
            # Get the original handler and its metadata
            handler = self.get_handler(name)
            metadata = handler.get_metadata()
            # Add the handler
            handler_class = handler.__class__
            trans_handler = handler_class()
            self.set_handler(trans_name, trans_handler,
                             **{'dc:language': language})

        message = self.gettext(u'Document translations created.')
        comeback(message, goto=';%s' % self.get_browse_view())


    #######################################################################
    # Add / New Resource
    new_resource_form__access__ = 'is_allowed_to_add'
    new_resource_form__label__ = u'Add'
    new_resource_form__sublabel__ = u'New Resource'
    def new_resource_form(self, context):
        type = context.get_form_value('type')
        if type is None:
            # Build the namespace
            namespace = {}
            namespace['types'] = []

            for handler_class in self.get_document_types():
                type_ns = {}
                gettext = handler_class.gettext
                format = urllib.quote(handler_class.class_id)
                type_ns['format'] = format
                icon = handler_class.class_icon48
                type_ns['icon'] = self.get_pathtoroot() + 'ui/' + icon
                title = handler_class.class_title
                type_ns['title'] = gettext(title)
                description = handler_class.class_description
                type_ns['description'] = gettext(description)
                type_ns['url'] = ';new_resource_form?type=' + format
                namespace['types'].append(type_ns)

            handler = self.get_handler('/ui/Folder_new_resource.xml')
            return stl(handler, namespace)

        else:
            handler_class = self.get_handler_class(type)
            return handler_class.new_instance_form()


    new_resource__access__ = 'is_allowed_to_add'
    def new_resource(self, context):
        class_id = context.get_form_value('class_id')
        name = context.get_form_value('name')
        title = context.get_form_value('dc:title')

        # Empty name?
        name = name.strip() or title.strip()
        if not name:
            message = u'The name must be entered'
            return context.come_back(replace)

        # Invalid name?
        name = checkid(name)
        if name is None:
            message = (u'The document name contains illegal characters,'
                       u' choose another one.')
            return context.come_back(message)

        # Find out the handler class
        handler_class = get_object_class(class_id)

        # Find out the name
        name = FileName.encode((name, handler_class.class_extension,
                                context.get_form_value('dc:language')))
        # Name already used?
        if self.has_handler(name):
            message = u'There is already another object with this name.'
            return context.come_back(message)

        # Build the handler
        handler = handler_class.new_instance()

        # Add the handler
        self.set_handler(name, handler)
        # Set the title
        handler = self.get_handler(name)
        root = self.get_site_root()
        languages = root.get_property('ikaaro:website_languages')
        handler.set_property('dc:title', title, languages[0])

        # Come back
        message = u'New resource added.'
        if context.has_form_value('add_and_return'):
            goto = ';%s' % self.get_browse_view()
        else:
            handler = self.get_handler(name)
            goto = './%s/;%s' % (name, handler.get_firstview())
        return context.come_back(message, goto=goto)


    browse_dir__access__ = 'is_authenticated'
    def browse_dir(self, context):
        namespace = {}
        namespace['bc'] = Breadcrumb(filter_type=File.File, start=self)

        # Avoid general template
        response = context.response
        response.set_header('Content-Type', 'text/html; charset=UTF-8')

        handler = self.get_handler('/ui/Folder_browsedir.xml')
        return stl(handler, namespace)


    #######################################################################
    # Add / Upload File
    upload_file__access__ = 'is_allowed_to_add'
    def upload_file(self, context):
        file = context.get_form_value('file')
        if file is None:
            return context.come_back(u'The file must be entered')

        # Build a memory resource
        mimetype = file.get_mimetype()

        # Guess the language if it is not included in the filename
        name = file.name
        if mimetype.startswith('text/'):
            short_name, type, language = FileName.decode(name)
            if language is None:
                # Guess the language
                file.open()
                data = file.read()
                file.close()
                encoding = Text.guess_encoding(data)
                data = unicode(data, encoding)
                language = i18n.oracle.guess_language(data)
                # Rebuild the name
                name = FileName.encode((short_name, type, language))

        # Invalid name?
        name = checkid(name)
        if name is None:
            return context.come_back(
                u'The document name contains illegal characters,'
                u' choose another one.')

        # Name already used?
        if self.has_handler(name):
            message = u'There is already another resource with this name.'
            return context.come_back(message)

        # Set the handler
        handler = build_handler(file)
        self.set_handler(name, handler, format=mimetype)

        # Come back
        if context.has_form_value('add_and_return'):
            goto = ';%s' % self.get_browse_view()
        else:
            goto='./%s/;%s' % (name, handler.get_firstview())
        goto = uri.get_reference(goto)
        message = self.gettext(u'File uploaded.')
        return goto.replace(message=message)


    #######################################################################
    # Search
    def get_search_criteria(self):
        """Return the criteria as a list of dictionnary
        like [{'id': criteria_id, 'title' : criteria_title},...]
        """
        return self.search_criteria


    def search(self, **kw):
        context = get_context()
        root = context.root
        catalog = root.get_handler('.catalog')
        result = catalog.search(**kw)
        return result


register_object_class(Folder)
register_object_class(Folder, format="application/x-not-regular-file")
