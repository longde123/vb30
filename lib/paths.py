#
# V-Ray For Blender
#
# http://chaosgroup.com
#
# Author: Andrei Izrantcev
# E-Mail: andrei.izrantcev@chaosgroup.com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# All Rights Reserved. V-Ray(R) is a registered trademark of Chaos Software.
#

import os

import bpy


# Get full file name (name.ext)
#
def GetFullFilename(filepath):
	return os.path.basename(bpy.path.abspath(filepath))


# Get file name (without .ext)
#
def GetFilename(filepath):
	fullFilename = GetFullFilename(filepath)
	filename, fileext = os.path.splitext(fullFilename)
	return filename


def unifyPath(filepath, relative=False):
	if relative:
		if filepath.startswith('//'):
			return filepath[2:].replace('\\', '/')

	filepath = os.path.normpath(bpy.path.abspath(filepath))
	filepath = filepath.replace('\\', '/')

	return filepath
