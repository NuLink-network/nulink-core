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


# Package Warnings #
####################


class DevelopmentInstallationRequired(RuntimeError):

    MESSAGE = '''
    A development installation of nulink is required to import {importable_name}. 
    Please follow the installation instructions published at:
    https://docs.nulink.org/en/latest/installation.html
    '''

    def __init__(self, importable_name: str, *args, **kwargs):
        msg = self.MESSAGE.format(importable_name=importable_name)
        super().__init__(msg, *args, **kwargs)
