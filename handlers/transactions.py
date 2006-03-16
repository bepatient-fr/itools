# -*- coding: ISO-8859-1 -*-
# Copyright (C) 2005 Juan David Ib��ez Palomar <jdavid@itaapy.com>
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
import datetime
import thread


thread_lock = thread.allocate_lock()


class Transaction(set):

    def rollback(self):
        if not self:
            return

        # Reset handlers
        for handler in self:
            handler.timestamp = datetime.datetime(1900, 1, 1)
        # Reset the transaction
        self.clear()


    def commit(self, username='', note=''):
        if not self:
            return

        # Event: before commit
        try:
            for handler in list(self):
                if hasattr(handler, 'before_commit'):
                    handler.before_commit()
        except:
            self.rollback()
            raise

        self.lock()
        try:
            # Errors should not happen in this stage.
            for handler in self:
                if handler.resource.get_mtime() is not None:
                    handler.resource.open()
                    handler._save_state(handler.resource)
                    handler.resource.close()
        except:
            # XXX Right now we just rollback the transaction, so handlers
            # state will be consistent.
            #
            # However, it may happen something worse, the resource layer
            # may be left into an inconsistent state.
            self.rollback()
            self.release()
            raise
        else:
            # Update handlers timestamp
            for handler in self:
                handler.timestamp = handler.resource.get_mtime()
            # Reset the transaction
            self.clear()
            # Release the thread lock
            self.release()


    def lock(self):
        thread_lock.acquire()


    def release(self):
        thread_lock.release()



_transactions = {}

def get_transaction():
    ident = thread.get_ident()

    thread_lock.acquire()
    try:
        transaction = _transactions.setdefault(ident, Transaction())
    finally:
        thread_lock.release()

    return transaction

