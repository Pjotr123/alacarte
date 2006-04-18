# -*- coding: utf-8 -*-
#   Alacarte Menu Editor - Simple fd.o Compliant Menu Editor
#   Copyright (C) 2006  Travis Watkins, Heinrich Wendel
#
#   This library is free software; you can redistribute it and/or
#   modify it under the terms of the GNU Library General Public
#   License as published by the Free Software Foundation; either
#   version 2 of the License, or (at your option) any later version.
#
#   This library is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#   Library General Public License for more details.
#
#   You should have received a copy of the GNU Library General Public
#   License along with this library; if not, write to the Free Software
#   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import os, re, xml.dom.minidom, locale
import gmenu
from Alacarte import util

class Menu:
	tree = None
	visible_tree = None
	path = None
	dom = None

class MenuEditor:
	def __init__(self):
		self.locale = locale.getdefaultlocale()[0]
		self.__loadMenus()

	def __loadMenus(self):
		self.applications = Menu()
		self.applications.tree = gmenu.lookup_tree('applications.menu', gmenu.FLAGS_SHOW_EMPTY|gmenu.FLAGS_INCLUDE_EXCLUDED|gmenu.FLAGS_INCLUDE_NODISPLAY)
		self.applications.visible_tree = gmenu.lookup_tree('applications.menu')
		self.applications.path = os.path.join(util.getUserMenuPath(), self.applications.tree.get_menu_file())
		if not os.path.isfile(self.applications.path):
			self.applications.dom = xml.dom.minidom.parseString(util.getUserMenuXml(self.applications.tree))
		else:
			self.applications.dom = xml.dom.minidom.parse(self.applications.path)
		self.__remove_whilespace_nodes(self.applications.dom)

		self.settings = Menu()
		self.settings.tree = gmenu.lookup_tree('settings.menu', gmenu.FLAGS_SHOW_EMPTY|gmenu.FLAGS_INCLUDE_EXCLUDED|gmenu.FLAGS_INCLUDE_NODISPLAY)
		self.settings.visible_tree = gmenu.lookup_tree('settings.menu')
		self.settings.path = os.path.join(util.getUserMenuPath(), self.settings.tree.get_menu_file())
		if not os.path.isfile(self.settings.path):
			self.settings.dom = xml.dom.minidom.parseString(util.getUserMenuXml(self.settings.tree))
		else:
			self.settings.dom = xml.dom.minidom.parse(self.settings.path)
		self.__remove_whilespace_nodes(self.settings.dom)

	def save(self):
		for menu in ('applications', 'settings'):
			fd = open(getattr(self, menu).path, 'w')
			fd.write(re.sub("\n[\s]*([^\n<]*)\n[\s]*</", "\\1</", getattr(self, menu).dom.toprettyxml().replace('<?xml version="1.0" ?>\n', '')))
			fd.close()
		self.__loadMenus()

	def getMenus(self, parent=None):
		if parent == None:
			yield self.applications.tree.root
			yield self.settings.tree.root
		else:
			for menu in parent.get_contents():
				if menu.get_type() == gmenu.TYPE_DIRECTORY:
					if menu.menu_id == 'Other' and len(menu.get_contents()) == 0:
						continue
					yield (menu, self.__isVisible(menu))

	def getItems(self, menu):
		for item in menu.get_contents():
			if item.get_type() == gmenu.TYPE_SEPARATOR:
				yield (item, True)
			else:
				if item.get_type() == gmenu.TYPE_ENTRY and item.get_desktop_file_id()[-19:] == '-usercustom.desktop':
					continue
				yield (item, self.__isVisible(item))

	def setVisible(self, item, visible):
		dom = self.__getMenu(item).dom
		if item.get_type() == gmenu.TYPE_ENTRY:
			menu_xml = self.__getXmlMenu(self.__getPath(item.get_parent()), dom, dom)
			if visible:
				self.__addXmlFilename(menu_xml, dom, item.get_desktop_file_id(), 'Include')
				self.__writeItem(item, no_display=False)
			else:
				self.__addXmlFilename(menu_xml, dom, item.get_desktop_file_id(), 'Exclude')
		elif item.get_type() == gmenu.TYPE_DIRECTORY:
			#don't mess with it if it's empty
			if len(item.get_contents()) == 0:
				return
			menu_xml = self.__getXmlMenu(self.__getPath(item), dom, dom)
			for node in self.__getXmlNodesByName(['Deleted', 'NotDeleted'], menu_xml):
				node.parentNode.removeChild(node)
			if visible:
				self.__writeMenu(item, no_display=False)
			else:
				self.__writeMenu(item, no_display=True)
		self.save()

	def hideItem(self, item):
		self.setVisible(item, False)

	def showItem(self, item):
		self.setVisible(item, True)

	def createItem(self, parent, icon, name, comment, command, use_term, before=None, after=None):
		file_id = self.__writeItem(None, icon, name, comment, command, use_term)
		dom = self.__getMenu(parent).dom
		self.__addItem(parent, file_id, dom, before, after)
		self.save()

	def createMenu(self, parent, icon, name, comment, before=None, after=None):
		file_id = self.__writeMenu(None, icon, name, comment)
		menu_id = file_id.rsplit('.', 1)[0]
		dom = self.__getMenu(parent).dom
		menu_xml = self.__getXmlMenu(self.__getPath(parent) + '/' + menu_id, dom, dom)
		self.__addXmlTextElement(menu_xml, 'Directory', file_id, dom)
		self.save()

	def editItem(self, item, icon, name, comment, command, use_term):
		#if nothing changed don't make a user copy
		if icon == item.get_icon() and name == item.get_name() and \
			comment == item.get_comment() and command == item.get_exec() and \
			use_term == item.get_launch_in_terminal():
			return
		self.__writeItem(item, icon, name, comment, command, use_term)
		self.save()

	def editMenu(self, menu, icon, name, comment):
		#if nothing changed don't make a user copy
		if icon == menu.get_icon() and name == menu.get_name() and comment == menu.get_comment():
			return
		#we don't use this, we just need to make sure the <Menu> exists
		#otherwise changes won't show up
		dom = self.__getMenu(menu).dom
		menu_xml = self.__getXmlMenu(self.__getPath(menu), dom, dom)
		self.__writeMenu(menu, icon, name, comment)
		self.save()

	def copyItem(self, item, new_parent, before=None, after=None):
		dom = self.__getMenu(new_parent).dom
		file_path = item.get_desktop_file_path()
		keyfile = util.DesktopParser(file_path)
		#erase Categories in new file
		keyfile.set('Categories', ('',))
		file_id = util.getUniqueFileId(item.get_name(), '.desktop')
		out_path = os.path.join(util.getUserItemPath(), file_id)
		keyfile.write(open(out_path, 'w'))
		self.__addItem(new_parent, file_id, dom)
		self.save()

	def moveItem(self, item, old_parent, new_parent, before=None, after=None):
		if old_parent != new_parent:
			#hide old item
			self.__writeItem(item, hidden=True)
			dom = self.__getMenu(new_parent).dom
			file_path = item.get_desktop_file_path()
			keyfile = util.DesktopParser(file_path)
			#erase Categories in new file
			keyfile.set('Categories', ('',))
			#make sure new item isn't hidden
			keyfile.set('Hidden', False)
			file_id = util.getUniqueFileId(item.get_name(), '.desktop')
			out_path = os.path.join(util.getUserItemPath(), file_id)
			keyfile.write(open(out_path, 'w'))
			self.__addItem(new_parent, file_id, dom)
			item = ('Item', file_id)
		if after or before:
			if after:
				index = new_parent.contents.index(after) + 1
			elif before:
				index = new_parent.contents.index(before)
			contents = new_parent.contents
			#if this is a move to a new parent you can't remove the item
			try:
				contents.remove(item)
			except:
				pass
			contents.insert(index, item)
			layout = self.__createLayout(contents)
			dom = self.__getMenu(new_parent).dom
			menu_xml = self.__getXmlMenu(self.__getPath(new_parent), dom, dom)
			self.__addXmlLayout(menu_xml, layout, dom)
		self.save()

	#private stuff
	def __getMenu(self, item):
		root = item.get_parent()
		while True:
			if root.get_parent():
				root = root.get_parent()
			else:
				break
		if root.menu_id == self.applications.tree.root.menu_id:
			return self.applications
		return self.settings

	def __isVisible(self, item):
		if item.get_type() == gmenu.TYPE_ENTRY:
			return not (item.get_is_excluded() or item.get_is_nodisplay())
		def loop_for_menu(parent, menu):
			for item in parent.get_contents():
				if item.get_type() == gmenu.TYPE_DIRECTORY:
					if item.menu_id == menu.menu_id:
						return True
					temp = loop_for_menu(item, menu)
					if temp:
						return True
			return False
		menu = self.__getMenu(item)
		if menu == self.applications:
			root = self.applications.visible_tree.root
		elif menu == self.settings:
			root = self.settings.visible_tree.root
		if item.get_type() == gmenu.TYPE_DIRECTORY:
			return loop_for_menu(root, item)
		return True

	def __getPath(self, menu, path=None):
		if not path:
			if self.__getMenu(menu) == self.applications:
				path = 'Applications'
			else:
				path = 'Desktop'
		if menu.get_parent():
			path = self.__getPath(menu.get_parent(), path)
			path += '/'
			path += menu.menu_id
		return path

	def __getXmlMenu(self, path, element, dom):
		if '/' in path:
			(name, path) = path.split('/', 1)
		else:
			name = path
			path = ''

		found = None
		for node in self.__getXmlNodesByName('Menu', element):
			for child in self.__getXmlNodesByName('Name', node):
				if child.childNodes[0].nodeValue == name:
					if path:
						found = self.__getXmlMenu(path, node, dom)
					else:
						found = node
					break
			if found:
				break
		if not found:
			node = self.__addXmlMenuElement(element, name, dom)
			if path:
				found = self.__getXmlMenu(path, node, dom)
			else:
				found = node

		return found

	def __addXmlMenuElement(self, element, name, dom):
		node = dom.createElement('Menu')
		self.__addXmlTextElement(node, 'Name', name, dom)
		return element.appendChild(node)

	def __addXmlTextElement(self, element, name, text, dom):
		node = dom.createElement(name)
		text = dom.createTextNode(text)
		node.appendChild(text)
		return element.appendChild(node)

	def __addXmlFilename(self, element, dom, filename, type = 'Include'):
		# remove old filenames
		for node in self.__getXmlNodesByName(['Include', 'Exclude'], element):
			if node.childNodes[0].nodeName == 'Filename' and node.childNodes[0].childNodes[0].nodeValue == filename:
				element.removeChild(node)

		# add new filename
		node = dom.createElement(type)
		node.appendChild(self.__addXmlTextElement(node, 'Filename', filename, dom))
		return element.appendChild(node)

	def __addDeleted(self, element, dom):
		node = dom.createElement('Deleted')
		return element.appendChild(node)

	def __writeItem(self, item=None, icon=None, name=None, comment=None, command=None, use_term=None, no_display=None, startup_notify=None, hidden=None):
		if item:
			file_path = item.get_desktop_file_path()
			file_id = item.get_desktop_file_id()
			keyfile = util.DesktopParser(file_path)
		elif item == None and name == None:
			raise Exception('New menu items need a name')
		else:
			file_id = util.getUniqueFileId(name, '.desktop')
			keyfile = util.DesktopParser()
		if icon:
			keyfile.set('Icon', icon)
			keyfile.set('Icon', icon, self.locale)
		if name:
			keyfile.set('Name', name)
			keyfile.set('Name', name, self.locale)
		if comment:
			keyfile.set('Comment', comment)
			keyfile.set('Comment', comment, self.locale)
		if command:
			keyfile.set('Exec', command)
		if use_term != None:
			keyfile.set('Terminal', use_term)
		if no_display != None:
			keyfile.set('NoDisplay', no_display)
		if startup_notify != None:
			keyfile.set('StartupNotify', startup_notify)
		if hidden != None:
			keyfile.set('Hidden', hidden)
		out_path = os.path.join(util.getUserItemPath(), file_id)
		keyfile.write(open(out_path, 'w'))
		return file_id

	def __writeMenu(self, menu=None, icon=None, name=None, comment=None, no_display=None):
		if menu:
			file_id = menu.get_menu_id() + '.directory'
			file_path = util.getDirectoryPath(file_id)
			keyfile = util.DesktopParser(file_path)
		elif menu == None and name == None:
			raise Exception('New menus need a name')
		else:
			file_id = util.getUniqueFileId(name, '.directory')
			keyfile = util.DesktopParser(file_type='Directory')
		if icon:
			keyfile.set('Icon', icon)
		if name:
			keyfile.set('Name', name)
			keyfile.set('Name', name, self.locale)
		if comment:
			keyfile.set('Comment', comment)
			keyfile.set('Comment', comment, self.locale)
		if no_display != None:
			keyfile.set('NoDisplay', no_display)
		out_path = os.path.join(util.getUserDirectoryPath(), file_id)
		keyfile.write(open(out_path, 'w'))
		return file_id

	def __getXmlNodesByName(self, name, element):
		for	child in element.childNodes:
			if child.nodeType == xml.dom.Node.ELEMENT_NODE and child.nodeName in name:
				yield child

	def __remove_whilespace_nodes(self, node):
		remove_list = []
		for child in node.childNodes:
			if child.nodeType == xml.dom.minidom.Node.TEXT_NODE:
				child.data = child.data.strip()
				if not child.data.strip():
					remove_list.append(child)
			elif child.hasChildNodes():
				self.__remove_whilespace_nodes(child)
		for node in remove_list:
			node.parentNode.removeChild(node)

	def __addXmlMove(self, element, old, new, dom):
		node = dom.createElement('Move')
		node.appendChild(self.__addXmlTextElement(node, 'Old', old))
		node.appendChild(self.__addXmlTextElement(node, 'New', new))
		return element.appendChild(node)

	def __addXmlLayout(self, element, layout, dom):
		# remove old layout
		for node in self.__getXmlNodesByName('Layout', element):
			element.removeChild(node)

		# add new layout
		node = dom.createElement('Layout')
		for order in layout.order:
			if order[0] == 'Separator':
				child = dom.createElement('Separator')
				node.appendChild(child)
			elif order[0] == 'Filename':
				child = self.__addXmlTextElement(node, 'Filename', order[1], dom)
			elif order[0] == 'Menuname':
				child = self.__addXmlTextElement(node, 'Menuname', order[1], dom)
			elif order[0] == 'Merge':
				child = dom.createElement('Merge')
				child.setAttribute('type', order[1])
				node.appendChild(child)
		return element.appendChild(node)

	def __createLayout(self, items):
		layout = Layout()
		layout.order = []

		layout.order.append(['Merge', 'menus'])
		for item in items:
			if isinstance(item, tuple):
				if item[0] == 'Separator':
					layout.parseSeparator()
				elif item[0] == 'Menu':
					layout.parseMenuname(item[1])
				elif item[0] == 'Item':
					layout.parseFilename(item[1])
			elif item.get_type() == gmenu.TYPE_DIRECTORY:
				layout.parseMenuname(item.get_menu_id())
			elif item.get_type() == gmenu.TYPE_ENTRY:
				layout.parseFilename(item.get_desktop_file_id())
			elif item.get_type() == gmenu.TYPE_SEPARATOR:
				layout.parseSeparator()
		layout.order.append(['Merge', 'files'])
		return layout

	#AFTER THIS STILL NOT PORTED
	def __addItem(self, parent, file_id, dom):
		xml_parent = self.__getXmlMenu(self.__getPath(parent), dom, dom)
		self.__addXmlFilename(xml_parent, dom, file_id, 'Include')
#		elif isinstance(entry, Menu):
#			parent.addSubmenu(entry)

#		if after or before:
#			self.__addLayout(parent)
#			self.__addXmlLayout(xml_parent, parent.Layout)

	def __deleteItem(self, parent, file_id, dom, before=None, after=None):
#		parent.Entries.remove(entry)

		xml_parent = self.__getXmlMenu(self.__getPath(parent), dom, dom)
		self.__addXmlFilename(xml_parent, dom, file_id, 'Exclude')

#		if isinstance(entry, MenuEntry):
#			entry.Parents.remove(parent)
#			parent.MenuEntries.remove(entry)
#			self.__addXmlFilename(xml_parent, entry.DesktopFileID, "Exclude")
#		elif isinstance(entry, Menu):
#			parent.Submenus.remove(entry)

#		if after or before:
#			self.__addLayout(parent)
#			self.__addXmlLayout(xml_parent, parent.Layout)

class Layout:
	"Menu Layout class"
	def __init__(self, node=None):
		self.order = []
		if node:
			self.show_empty = node.getAttribute("show_empty") or "false"
			self.inline = node.getAttribute("inline") or "false"
			self.inline_limit = node.getAttribute("inline_limit") or 4
			self.inline_header = node.getAttribute("inline_header") or "true"
			self.inline_alias = node.getAttribute("inline_alias") or "false"
			self.inline_limit = int(self.inline_limit)
			self.parseNode(node)
		else:
			self.show_empty = "false"
			self.inline = "false"
			self.inline_limit = 4
			self.inline_header = "true"
			self.inline_alias = "false"
			self.order.append(["Merge", "menus"])
			self.order.append(["Merge", "files"])

	def parseNode(self, node):
		for child in node.childNodes:
			if child.nodeType == ELEMENT_NODE:
				if child.tagName == "Menuname":
					try:
						self.parseMenuname(
							child.childNodes[0].nodeValue,
							child.getAttribute("show_empty") or "false",
							child.getAttribute("inline") or "false",
							child.getAttribute("inline_limit") or 4,
							child.getAttribute("inline_header") or "true",
							child.getAttribute("inline_alias") or "false" )
					except IndexError:
						raise ValidationError('Menuname cannot be empty', "")
				elif child.tagName == "Separator":
					self.parseSeparator()
				elif child.tagName == "Filename":
					try:
						self.parseFilename(child.childNodes[0].nodeValue)
					except IndexError:
						raise ValidationError('Filename cannot be empty', "")
				elif child.tagName == "Merge":
					self.parseMerge(child.getAttribute("type") or "all")

	def parseMenuname(self, value, empty="false", inline="false", inline_limit=4, inline_header="true", inline_alias="false"):
		self.order.append(["Menuname", value, empty, inline, inline_limit, inline_header, inline_alias])
		self.order[-1][4] = int(self.order[-1][4])

	def parseSeparator(self):
		self.order.append(["Separator"])

	def parseFilename(self, value):
		self.order.append(["Filename", value])

	def parseMerge(self, type="all"):
		self.order.append(["Merge", type])
