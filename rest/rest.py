# -*- coding: UTF-8 -*-
# Copyright (C) 2007 Hervé Cauwelier <herve@itaapy.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Import from the Standard Library
import cgi

# Import from itools
from itools.xml import (TEXT, COMMENT, START_ELEMENT, END_ELEMENT, get_element,
    stream_to_str as stream_to_str_as_xml)
from itools.xhtml import (xhtml_uri, stream_to_str_as_xhtml,
    stream_to_str_as_html)
from parser import Document as RestDocument, parse_inline


# XXX dummy
rest_uri = 'http://docutils.sourceforge.net/docs/ref/docutils.dtd'



def block_stream(text):
    """Turn a text into a list of events similar to XML: START_ELEMENT,
    END_ELEMENT, TEXT.

    Block elements (lists, literal blocks, paragraphs, titles...) are
    concerned. Inline elements are loaded as well where applicable.
    """
    events = []

    for event, value in RestDocument(text):
        if event == 'title':
            overline, title, underline = value
            target = checkid(title).lower()
            attributes = {(rest_uri, 'overline'): overline,
                          (rest_uri, 'underline'): underline,
                          (rest_uri, 'target'): target}
            events.append((START_ELEMENT, (rest_uri, event, attributes), None))
            events.extend(inline_stream(title))
            events.append((END_ELEMENT, (rest_uri, event), None))
        elif event == 'paragraph':
            events.append((START_ELEMENT, (rest_uri, event, {}), None))
            events.extend(inline_stream(value))
            events.append((END_ELEMENT, (rest_uri, event), None))
        elif event == 'literal_block':
            events.append((START_ELEMENT, (rest_uri, event, {}), None))
            events.append((TEXT, value.encode('utf-8'), None))
            events.append((END_ELEMENT, (rest_uri, event), None))
        elif event == 'list_begin':
            events.append((START_ELEMENT, (rest_uri, 'list',
                {(rest_uri, 'item'): value}), None))
        elif event == 'list_end':
            events.append((END_ELEMENT, (rest_uri, 'list'), None))
        elif event == 'list_item_begin':
            events.append((START_ELEMENT, (rest_uri, 'list_item', {}), None))
        elif event == 'list_item_end':
            events.append((END_ELEMENT, (rest_uri, 'list_item'), None))
        else:
            raise NotImplementedError, event

    return events



def inline_stream(text):
    """Turn a text into a list of events similar to XML: START_ELEMENT,
    END_ELEMENT, TEXT.

    Inline elements (emphasis, strong, reference sources...) are concerned.
    """
    events = []

    for event, value in parse_inline(text):
        if event == 'text':
            events.append((TEXT, value.encode('utf-8'), None))
        elif event == 'footnote':
            target = checkid(value).lower()
            attributes = {'target': target}
            events.append((START_ELEMENT, (rest_uri, event, attributes), None))
            events.append((TEXT, value.encode('utf-8'), None))
            events.append((END_ELEMENT, (rest_uri, event), None))
        elif event == 'reference':
            target = checkid(value).lower()
            attributes = {'target': target}
            events.append((START_ELEMENT, (rest_uri, event, attributes), None))
            events.append((TEXT, value.encode('utf-8'), None))
            events.append((END_ELEMENT, (rest_uri, event), None))
        else:
            events.append((START_ELEMENT, (rest_uri, event, {}), None))
            events.append((TEXT, value.encode('utf-8'), None))
            events.append((END_ELEMENT, (rest_uri, event), None))

    return events



def to_xhtml_stream(stream):
    title_levels = []
    last_title_level = None
    list_items = []
    one_to_one = {'paragraph': 'p',
                  'literal_block': 'pre',
                  'list_item': 'li',
                  'strong': 'strong',
                  'emphasis': 'em',
                  'literal': 'tt'}

    events = []
    for event, value, line in stream:
        if event == TEXT:
            data = cgi.escape(value)
            events.append((event, data, line))
        elif event == START_ELEMENT:
            _, name, attributes = value
            attr = {}
            if name == 'title':
                overline = attributes[(rest_uri, 'overline')]
                underline = attributes[(rest_uri, 'underline')]
                if (overline, underline) in title_levels:
                    level = title_levels.index((overline, underline))
                else:
                    level = len(title_levels)
                    title_levels.append((overline, underline))
                # Add an Anchor to this section
                attr[(xhtml_uri, 'name')] = attributes[(rest_uri, 'target')]
                events.append((event, (xhtml_uri, 'a', attr), line))
                events.append((END_ELEMENT, (xhtml_uri, 'a'), line))
                # index 0 -> <h1>
                level += 1
                tag = 'h%d' % level
                attr = {}
                last_title_level = level
            elif name=='footnote':
                target = '#id%s' % str(attributes['target'])
                tag = 'a'
                attr[(xhtml_uri, 'href')] = target
                events.append((event, (xhtml_uri, tag), None))
                tag = None
                # Add the character [
                events.append((TEXT, '[', line))
            elif name=='reference':
                tag = 'a'
                target = attributes['target']
                attr[(xhtml_uri, 'href')] = '#%s' % target
            elif name=='list':
                item = attributes[(rest_uri, 'item')]
                if item == u'#':
                    tag = 'ol'
                else:
                    tag = 'ul'
                list_items.append(item)
            elif name in ('document',):
                tag = None
            else:
                tag = one_to_one[name]
            if tag:
                events.append((event, (xhtml_uri, tag, attr), line))
        elif event == END_ELEMENT:
            _, name = value
            if name == 'title':
                tag = 'h%d' % last_title_level
            elif name == 'footnote':
                events.append((TEXT, ']', line))
                tag = 'a'
            elif name == 'reference':
                tag = 'a'
            elif name == 'list':
                if list_items.pop() == u'#':
                    tag = 'ol'
                else:
                    tag = 'ul'
            elif name in ('document',):
                tag = None
            else:
                tag = one_to_one[name]

            if tag:
                events.append((event, (xhtml_uri, tag), None))

    return events



def stream_to_str_as_latex(stream):
    buffer = []
    title_levels = []
    list_items = []
    sections = {0: 'section',
                1: 'subsection',
                2: 'subsubsection',
                3: 'paragraph',
                4: 'subparagraph'}
    title_open = False
    verbatim_open = False

    for event, value, line in stream:
        if event == TEXT:
            data = value
            if verbatim_open is False:
                data = data.replace('_', '\_')
                data = data.replace('$', '\$')
                data = data.replace('#', '\#')
                data = data.replace('&', '\&')
            buffer.append(data)
            if title_open is True:
                buffer.append('}\n')
                title_open = False
        elif event == START_ELEMENT:
            _, name, attributes = value
            if name == 'title':
                overline = attributes[(rest_uri, 'overline')]
                underline = attributes[(rest_uri, 'underline')]
                if (overline, underline) in title_levels:
                    level = title_levels.index((overline, underline))
                else:
                    level = len(title_levels)
                    title_levels.append((overline, underline))
                section = sections[level]
                buffer.append('\\%s{' % section)
                title_open = True
            if name == 'list':
                item = attributes[(rest_uri, 'item')]
                if item == u'#':
                    buffer.append('\\begin{enumerate}\n')
                else:
                    buffer.append('\\begin{itemize}\n')
                list_items.append(item)
            elif name == 'list_item':
                buffer.append('\item ')
            elif name == 'literal_block':
                buffer.append('\\begin{verbatim}\n')
                verbatim_open = True
            elif name == 'paragraph':
                buffer.append('\n')
            elif name == 'emphasis':
                buffer.append('{\\em ')
            elif name == 'strong':
                buffer.append('{\\bf ')
            elif name == 'literal':
                buffer.append('{\\tt ')
        elif event == END_ELEMENT:
            _, name = value
            # No end of title/section
            if name == 'list':
                if list_items.pop() == u'#':
                    buffer.append('\\end{enumerate}\n')
                else:
                    buffer.append('\\end{itemize}\n')
            elif name == 'list_item':
                buffer.append('\n')
            elif name == 'literal_block':
                buffer.append('\n\\end{verbatim}\n')
                verbatim_open = False
            elif name == 'paragraph':
                buffer.append('\n')
            elif name in ('emphasis', 'strong', 'literal'):
                buffer.append('}')

    return ''.join(buffer)



###########################################################################
# API Public
###########################################################################
src = ur"""ÄÅÁÀÂÃäåáàâãÇçÉÈÊËéèêëæÍÌÎÏíìîïÑñÖÓÒÔÕØöóòôõøßÜÚÙÛüúùûÝŸýÿ"""
dst = ur"""AAAAAAaaaaaaCcEEEEeeeeeIIIIiiiiNnOOOOOOooooooSUUUUuuuuYŸyy"""

transmap = {}
for i in range(len(src)):
    a, b = src[i], dst[i]
    transmap[ord(a)] = ord(b)


def checkid(id):
    """
    Turn a bytestring or unicode into an identifier only composed of
    alphanumerical characters and a limited list of signs.

    It only supports Latin-based alphabets.
    """
    if isinstance(id, str):
        id = unicode(id, 'utf8')

    # Strip diacritics
    id = id.strip().translate(transmap)

    # Check for unallowed characters
    allowed_characters = set([u'.', u'-', u'_', u'@'])
    id = [ (c.isalnum() or c in allowed_characters) and c or u'-' for c in id ]

    # Merge hyphens
    id = u''.join(id)
    id = id.split(u'-')
    id = u'-'.join([x for x in id if x])

    # Check wether the id is empty
    if len(id) == 0:
        return None

    # Return a safe ASCII bytestring
    return str(id)



def to_html_events(text):
    events = block_stream(text)
    return to_xhtml_stream(events)


def to_str(text, format, encoding='utf-8'):
##    if format == 'rest':
##        raise NotImplementedError
    if format == 'xml':
        events = block_stream(text)
        return stream_to_str_as_xml(events, encoding)
    elif format == 'xhtml':
        events = to_html_events(text)
        return stream_to_str_as_xhtml(events, encoding)
    elif format == 'html':
        events = to_html_events(text)
        return stream_to_str_as_html(events, encoding)
    elif format == 'latex':
        events = block_stream(text)
        return stream_to_str_as_latex(events, encoding)
    else:
        raise ValueError, "unexpected format '%s'" % format

###########################################################################
# API Public (XXX for backwards compatibility)
###########################################################################
def to_xml(text, encoding='UTF-8'):
    return to_str(text, 'xml', encoding)


def to_html(text, encoding='UTF-8'):
    return to_str(text, 'xhtml', encoding)


def to_latex(text, encoding='UTF-8'):
    return to_str(text, 'latex', encoding)
