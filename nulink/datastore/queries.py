"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import functools
from typing import Callable, List, Type

from nulink.datastore.base import DatastoreRecord
from nulink.datastore.datastore import Datastore, DatastoreQueryResult, RecordNotFound
from nulink.datastore.models import ReencryptionRequest


def unwrap_records(func: Callable[..., DatastoreQueryResult]) -> Callable[..., List[Type['DatastoreRecord']]]:
    """
    Used to safely unwrap results of a query.
    Suitable only for reading `DatastoreRecord`s. Use `find_*` functions if you want to modify records.

    Since results returned by `Datastore.query_by()` are lazy (wrapped in a `@contextmanager` generator)
    we have to unwrap them and handle `RecordNotFound` error, if any. `DatastoreRecord`s are not writable
    after unwrapping, because exiting `@contextmanager` is also closing `Datastore` transaction.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> List[Type['DatastoreRecord']]:
        try:
            with func(*args, **kwargs) as results:
                return results
        except RecordNotFound:
            return []

    return wrapper


@unwrap_records
def get_reencryption_requests(ds: Datastore) -> List[ReencryptionRequest]:
    return ds.query_by(ReencryptionRequest)
