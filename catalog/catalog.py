# -*- coding: UTF-8 -*-
# Copyright (C) 2004-2006 Juan David IbÃ¡Ã±ez Palomar <jdavid@itaapy.com>
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA

# Import from the future
from __future__ import with_statement

# Import from the Standard Library
from operator import itemgetter

# Import from itools
from itools.uri import get_absolute_reference
from itools import vfs
from itools.handlers.base import Handler
from itools.handlers.Folder import Folder
from index import Index
from documents import Documents, Document
from analysers import get_analyser
import queries



class Field(object):

    __slots__ = ['number', 'name', 'type', 'is_indexed', 'is_stored']


    def __init__(self, number, name, type, is_indexed, is_stored):
        self.number = number
        self.name = name
        self.type = type
        self.is_indexed = is_indexed
        self.is_stored = is_stored



class SearchResults(object):

    __slots__ = ['results', 'documents', 'field_numbers']


    def __init__(self, results, documents, field_numbers):
        self.results = results
        self.documents = documents
        self.field_numbers = field_numbers


    def get_n_documents(self):
        """Returns the number of documents found."""
        return len(self.results)


    def get_documents(self):
        # Iterate on sorted by weight in decrease order
        get_document = self.documents.get_document
        field_numbers = self.field_numbers
        for document in sorted(self.results.iteritems(), key=itemgetter(1),
                               reverse=True):
            doc_number = document[0]
            # Load the document
            document = get_document(doc_number)
            document.field_numbers = field_numbers
            yield document 



class Catalog(Folder):

    class_version = '20060708'

    __slots__ = ['uri', 'timestamp', 'parent', 'name', 'real_handler',
                 'fields', 'field_numbers', 'indexes', 'documents']


    def new(self, fields=[]):
        self.fields = []
        self.field_numbers = {}
        # The indexes
        self.indexes = []
        for number, field in enumerate(fields):
            name, type, is_indexed, is_stored = field
            # Keep field metadata
            field = Field(number, name, type, is_indexed, is_stored)
            self.fields.append(field)
            # Keep a mapping from field name to field number
            self.field_numbers[name] = number
            # Initialize index
            if is_indexed:
                self.indexes.append(Index())
            else:
                self.indexes.append(None)
        # Initialize documents
        self.documents = Documents()


    #########################################################################
    # Load / Save
    #########################################################################
    def _load_state(self):
        self.fields = []
        self.field_numbers = {}
        self.indexes = []
        self.documents = None
        # Load
        base = vfs.open(self.uri)
        with base.open('fields') as file:
            for line in file.readlines():
                line = line.strip()
                if not line:
                    continue
                number, name, type, is_indexed, is_stored = line.split('#')
                number = int(number)
                is_indexed = bool(int(is_indexed))
                is_stored = bool(int(is_stored))
                field = Field(number, name, type, is_indexed, is_stored)
                self.fields.append(field)
                self.field_numbers[name] = number
        # Initialize the indexes
        for field in self.fields:
            if field.is_indexed:
                index_uri = self.uri.resolve2('index_%d' % field.number)
                self.indexes.append(Index(index_uri))
            else:
                self.indexes.append(None)
        # Initialize the documents
        documents_uri = self.uri.resolve2('documents')
        self.documents = Documents(documents_uri)


    def save_state_to(self, uri):
        uri = get_absolute_reference(uri)
        # Initialize
        vfs.make_folder(uri)
        # Create the fields metadata file        
        base = vfs.open(uri)
        with base.make_file('fields') as file:
            for field in self.fields:
                file.write('%d#%s#%s#%d#%d\n' % (field.number, field.name,
                                                 field.type, field.is_indexed,
                                                 field.is_stored))
        # Save the indexes
        for field_number, index in enumerate(self.indexes):
            if index is None:
                continue
            index_uri = uri.resolve2('index_%d' % field_number)
            index.save_state_to(index_uri)
        # Save the documents
        documents_uri = uri.resolve2('documents')
        self.documents.save_state_to(documents_uri)


    def save_state(self):
        # The indexes
        for index in self.indexes:
            if index is not None:
                index.save_state()
        # The documents
        self.documents.save_state()
        # Update the timestamp
        self.timestamp = vfs.get_mtime(self.uri)


    copy_handler = Handler.copy_handler


    #########################################################################
    # Public API
    #########################################################################
    def get_index(self, name):
        field_numbers = self.field_numbers
        # Check the field exists
        if name not in field_numbers:
            raise ValueError, 'the field "%s" is not defined' % name
        # Get the index
        number = field_numbers[name]
        index = self.indexes[number]
        # Check the field is indexed
        if index is None:
            raise ValueError, 'the field "%s" is not indexed' % name

        return index


    def index_document(self, document):
        self.set_changed()
        # Create the document to index
        doc_number = self.documents.n_documents
        catalog_document = Document(doc_number)

        # Define the function to get values from the document
        if isinstance(document, dict):
            getter = document.get
        else:
            getter = lambda x: getattr(document, x, None)

        # Index
        for field in self.fields:
            # Extract the field value from the document
            value = getter(field.name)

            # If value is None, don't go further
            if value is None:
                continue

            # Update the Inverted Index
            if field.is_indexed:
                index = self.indexes[field.number]
                # Tokenize
                terms = set()
                analyser = get_analyser(field.type)
                for word, position in analyser(value):
                    terms.add(word)
                    # Update the inverted index
                    index.index_term(word, doc_number, position)

            # Update the Document
            if field.is_stored:
                # Stored
                # XXX Coerce
                if isinstance(value, list):
                    value = u' '.join(value)
                elif isinstance(value, str):
                    value = unicode(value)
                catalog_document.fields[field.number] = value
            else:
                # Not Stored
                catalog_document.fields[field.number] = list(terms)

        # Add the Document
        self.documents.index_document(catalog_document)

        return doc_number


    def unindex_document(self, doc_number):
        self.set_changed()
        # Update the indexes
        document = self.documents.get_document(doc_number)
        for field in self.fields:
            # Check the field is indexed
            if not field.is_indexed:
                continue
            # Check the document is indexed for that field
            value = document.fields.get(field.number)
            if value is None:
                continue
            # If the field is stored, find out the terms to unindex
            if field.is_stored:
                analyser = get_analyser(field.type)
                terms = [ term for term, position in analyser(value) ]
                terms = set(terms)
            else:
                terms = value
            # Unindex
            index = self.indexes[field.number]
            for term in terms:
                index.unindex_term(term, doc_number)

        # Update the documents
        self.documents.unindex_document(doc_number)


    def search(self, query=None, **kw):
        # Build the query if it is passed through keyword parameters
        if query is None:
            if kw:
                atoms = []
                for key, value in kw.items():
                    atoms.append(queries.Phrase(key, value))

                query = queries.And(*atoms)
            else:
                raise ValueError, "expected a query"
        # Search
        results = query.search(self)
        return SearchResults(results, self.documents, self.field_numbers)

