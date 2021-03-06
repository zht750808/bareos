#   BAREOS - Backup Archiving REcovery Open Sourced
#
#   Copyright (C) 2019-2020 Bareos GmbH & Co. KG
#
#   This program is Free Software; you can redistribute it and/or
#   modify it under the terms of version three of the GNU Affero General Public
#   License as published by the Free Software Foundation and included
#   in the file LICENSE.
#
#   This program is distributed in the hope that it will be useful, but
#   WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#   02110-1301, USA.

# -*- coding: utf-8 -*-

from sphinx.domains import Domain, ObjType
from sphinx.roles import XRefRole
from sphinx.domains.std import GenericObject, StandardDomain
from sphinx.directives import ObjectDescription
from sphinx.util.nodes import clean_astext, make_refnode
from sphinx.util import logging
from sphinx.util import ws_re
from sphinx import addnodes
from sphinx.util.docfields import Field
from docutils import nodes
from pprint import pformat
import re

#
# modifies the default rule for rendering
# .. config::option:
#
# Also modifes the generated index.
# If this extension is not loaded,
# index will be 'command line option' ...
#

# phpmyadmin:
# anchor: #cfg_DirJobAlwaysIncrementalMaxFullAge
# index:  configuration option: ...

# see
# https://github.com/sphinx-doc/sphinx/blob/master/sphinx/directives/__init__.py
# https://www.sphinx-doc.org/en/master/extdev/domainapi.html

#
# Adapted for Bareos:
#
# anchor: #config-{daemon}_{resource}_{CamelCaseDirective}
# config-Director_Job_AlwaysIncrementalMaxFullAge
# index:  Configuration Directive; {directive} ({daemon}->{resource})

# TODO
# currently only adapted option. section must still be adapted.


def uppercaseFirstLetter(text):
    # Make sure, string starts with an upppercase letter.
    if len(text) >= 1:
        if text[0] != text[0].upper():
            resulttext = text[0].upper() + text[1:]
            return resulttext
    return text


def convertCamelCase2Spaces(valueCC):
    s1 = re.sub("([a-z0-9])([A-Z])", r"\1 \2", valueCC)
    result = []
    for token in s1.split(" "):
        u = token.upper()
        if u in [
            "ACL",
            "CA",
            "CN",
            "DB",
            "DH",
            "FD",
            "FS",
            "LMDB",
            "NDMP",
            "PSK",
            "SD",
            "SSL",
            "TLS",
            "VSS",
        ]:
            token = u
        result.append(token)

    return " ".join(result)


def get_config_directive(text):
    """
    This function generates from the signature
    the different required formats of a configuration directive.
    The signature (text) must be given (depending on the type) as:

    <dir|sd|fd|console>/<resourcetype_lower_case>/<DirectiveInCamelCase> = <value>

    Examples for the different types:

    Daemon:
    dir

    Resource Type:
    dir/job

    Resource Name:
    dir/job = backup-client1

    (Reference to a) Resource Directive:
    dir/job/TlsAlwaysIncrementalMaxFullAcl

    Resource Directive With Value:
    dir/job/TlsAlwaysIncrementalMaxFullAcl = False
    """

    logger = logging.getLogger(__name__)

    templates = {
        1: {"shortid": u"{Daemon}", "display": u"{Daemon}"},
        2: {
            "shortid": u"{Resource}",
            # Resource-Type
            "display": u"{Resource} ({Dmn})",
            # Resource-Name
            "displayWithValue": u"{value} ({Dmn}->{Resource})",
        },
        3: {
            "shortid": u"{Directive}",
            "display": u"{Directive} ({Dmn}->{Resource})",
            "displayWithValue": u"{Directive} ({Dmn}->{Resource}) = {value}",
            "indextemplate": u"Configuration Directive; {Directive} ({Dmn}->{Resource})",
            "internaltargettemplate": u"{dmn}/{resource}/{CamelCaseDirective}",
            # Latex: directiveDirJobCancel%20Lower%20Level%20Duplicates
            # The follow targettemplate will create identical anchors as Latex,
            # but as the base URL is likly it be different, it does not help (and still looks ugly).
            # targettemplate = u'directive{dmn}{resource}{directive}'
            "targettemplate": u"config-{Dmn}_{Resource}_{CamelCaseDirective}",
        },
        4: {
            "shortid": u"{Sub1}",
            "display": u"{Sub1} ({Dmn}->{Resource}->{Directive})",
            "displayWithValue": u"{Sub1} ({Dmn}->{Resource}->{Directive}) = {value}",
            "indextemplate": u"Configuration Directive; {Sub1} ({Dmn}->{Resource}->{Directive})",
            "internaltargettemplate": u"{dmn}/{resource}/{CamelCaseDirective}/{CamelCaseSub1}",
            "targettemplate": u"config-{Dmn}_{Resource}_{CamelCaseDirective}_{CamelCaseSub1}",
        },
        5: {
            "shortid": u"{Sub2}",
            "display": u"{Sub2} ({Dmn}->{Resource}->{Directive}->{Sub1})",
            "displayWithValue": u"{Sub2} ({Dmn}->{Resource}->{Directive}->{Sub1}) = {value}",
            "indextemplate": u"Configuration Directive; {Sub2} ({Dmn}->{Resource}->{Directive}->{Sub1})",
            "internaltargettemplate": u"{dmn}/{resource}/{CamelCaseDirective}/{CamelCaseSub1}/{CamelCaseSub2}",
            "targettemplate": u"config-{Dmn}_{Resource}_{CamelCaseDirective}_{CamelCaseSub1}_{CamelCaseSub2}",
        },
    }

    result = {"signature": text}

    try:
        key, value = text.split("=", 1)
        result["value"] = value.strip()
    except ValueError:
        # fall back
        key = text

    inputComponent = key.strip().split("/", 4)
    components = len(inputComponent)

    if components >= 1:
        daemon = inputComponent[0].lower()
        if daemon == "director" or daemon == "dir":
            result["Daemon"] = "Director"
            result["dmn"] = "dir"
            result["Dmn"] = "Dir"
        elif daemon == "storage daemon" or daemon == "storage" or daemon == "sd":
            result["Daemon"] = "Storage Daemon"
            result["dmn"] = "sd"
            result["Dmn"] = "Sd"
        elif daemon == "file daemon" or daemon == "file" or daemon == "fd":
            result["Daemon"] = "File Daemon"
            result["dmn"] = "fd"
            result["Dmn"] = "Fd"
        elif daemon == "bconsole" or daemon == "console":
            result["Daemon"] = "Console"
            result["dmn"] = "console"
            result["Dmn"] = "Console"
        else:
            # TODO: raise
            result["Daemon"] = "UNKNOWN"
            result["dmn"] = "UNKNOWN"
            result["Dmn"] = "UNKNOWN"

    if components >= 2:
        result["resource"] = inputComponent[1].replace(" ", "").lower()
        result["Resource"] = inputComponent[1].replace(" ", "").capitalize()

    if components >= 3:
        # input_directive should be without spaces.
        # However, we make sure, by removing all spaces.
        result["CamelCaseDirective"] = uppercaseFirstLetter(
            inputComponent[2].replace(" ", "")
        )
        result["Directive"] = convertCamelCase2Spaces(result["CamelCaseDirective"])

        if components >= 4:
            # e.g. fileset include/exclude directive
            # dir/fileset/include/File
            result["CamelCaseSub1"] = uppercaseFirstLetter(
                inputComponent[3].replace(" ", "")
            )
            result["Sub1"] = convertCamelCase2Spaces(result["CamelCaseSub1"])

        if components >= 5:
            # e.g. fileset include options
            # dir/fileset/include/options/basejob
            result["CamelCaseSub2"] = uppercaseFirstLetter(
                inputComponent[4].replace(" ", "")
            )
            result["Sub2"] = convertCamelCase2Spaces(result["CamelCaseSub2"])

        result["indexentry"] = templates[components]["indextemplate"].format(**result)
        result["target"] = templates[components]["targettemplate"].format(**result)
        result["internaltarget"] = templates[components][
            "internaltargettemplate"
        ].format(**result)

    result["shortid"] = templates[components]["shortid"].format(**result)
    if "value" in result:
        result["displayname"] = templates[components]["displayWithValue"].format(
            **result
        )
    else:
        result["displayname"] = templates[components]["display"].format(**result)

    # logger.debug('[bareos] ' + pformat(result))

    return result


class ConfigOption(ObjectDescription):
    parse_node = None

    has_arguments = True

    doc_field_types = [
        Field("required", label="Required", has_arg=False, names=("required",)),
        Field("type", label="Type", has_arg=False, names=("type",)),
        Field("default", label="Default value", has_arg=False, names=("default",)),
        Field("version", label="Since Version", has_arg=False, names=("version",)),
        Field("deprecated", label="Deprecated", has_arg=False, names=("deprecated",)),
        Field("alias", label="Alias", has_arg=False, names=("alias",)),
    ]

    def handle_signature(self, sig, signode):
        directive = get_config_directive(sig)
        signode.clear()
        # only show the directive (not daemon and resource type)
        signode += addnodes.desc_name(sig, directive["shortid"])
        # normalize whitespace like XRefRole does
        name = ws_re.sub("", sig)
        return name

    def add_target_and_index(self, name, sig, signode):
        """
        Usage:

        .. config:option:: dir/job/TlsEnable

           :required: True
           :type: Boolean
           :default: False
           :version: 16.2.4

           Multiline description ...

        The first argument specifies the directive and must be givenin following syntax:
        config::option:: <dir|sd|fd|console>/<resourcetype_lower_case>/<DirectiveInCamelCase>

        doc_field_types are only written when they should be displayed:
        :required: True
        :type: Boolean
        :default: False
        :version: 16.2.4
        :deprecated: True
        'alias: True

        To refer to this description, use
        :config:option:`dir/job/TlsEnable`.
        """

        directive = get_config_directive(sig)

        targetname = directive["target"]
        signode["ids"].append(targetname)
        self.state.document.note_explicit_target(signode)

        if "indexentry" in directive:
            indextype = "single"
            # Generic index entries
            self.indexnode["entries"].append(
                (indextype, directive["indexentry"], targetname, targetname, None)
            )

        self.env.domaindata["config"]["objects"][self.objtype, sig] = (
            self.env.docname,
            targetname,
        )


class ConfigOptionXRefRole(XRefRole):
    """
    Cross-referencing role for configuration options (adds an index entry).
    """

    def result_nodes(self, document, env, node, is_ref):
        logger = logging.getLogger(__name__)
        # logger.debug('[bareos] is_ref: {}, node[reftarget]: {}, {}'.format(str(is_ref), node['reftarget'], type(node['reftarget'])))
        # logger.debug('[bareos] ' + pformat(result))

        if not is_ref:
            return [node], []

        varname = node["reftarget"]
        directive = get_config_directive(varname)

        if not "indexentry" in directive:
            return [node], []

        tgtid = "index-%s" % env.new_serialno("index")

        indexnode = addnodes.index()
        indexnode["entries"] = [
            ("single", directive["indexentry"], tgtid, varname, None)
        ]
        targetnode = nodes.target("", "", ids=[tgtid])
        document.note_explicit_target(targetnode)

        return [indexnode, targetnode, node], []

    def process_link(self, env, refnode, has_explicit_title, title, target):

        logger = logging.getLogger(__name__)

        if has_explicit_title:
            return title, target

        directive = get_config_directive(title)
        # logger.debug('process_link({}, {})'.format(title, target))
        # logger.debug('process_link: ' + pformat(directive))

        if "internaltarget" in directive:
            return directive["displayname"], directive["internaltarget"]
        else:
            return directive["displayname"], target


class ConfigSection(ObjectDescription):
    indextemplate = "configuration section; %s"
    parse_node = None

    def handle_signature(self, sig, signode):
        if self.parse_node:
            name = self.parse_node(self.env, sig, signode)
        else:
            signode.clear()
            signode += addnodes.desc_name(sig, sig)
            # normalize whitespace like XRefRole does
            name = ws_re.sub("", sig)
        return name

    def add_target_and_index(self, name, sig, signode):
        targetname = "%s-%s" % (self.objtype, name)
        signode["ids"].append(targetname)
        self.state.document.note_explicit_target(signode)
        if self.indextemplate:
            colon = self.indextemplate.find(":")
            if colon != -1:
                indextype = self.indextemplate[:colon].strip()
                indexentry = self.indextemplate[colon + 1 :].strip() % (name,)
            else:
                indextype = "single"
                indexentry = self.indextemplate % (name,)
            self.indexnode["entries"].append(
                (indextype, indexentry, targetname, targetname, None)
            )
        self.env.domaindata["config"]["objects"][self.objtype, name] = (
            self.env.docname,
            targetname,
        )


class ConfigSectionXRefRole(XRefRole):
    """
    Cross-referencing role for configuration sections (adds an index entry).
    """

    def result_nodes(self, document, env, node, is_ref):
        if not is_ref:
            return [node], []
        varname = node["reftarget"]
        tgtid = "index-%s" % env.new_serialno("index")
        indexnode = addnodes.index()
        indexnode["entries"] = [
            ("single", varname, tgtid, varname, None),
            ("single", "configuration section; %s" % varname, tgtid, varname, None),
        ]
        targetnode = nodes.target("", "", ids=[tgtid])
        document.note_explicit_target(targetnode)
        return [indexnode, targetnode, node], []


class ConfigFileDomain(Domain):
    name = "config"
    label = "Config"

    object_types = {
        "option": ObjType("config option", "option"),
        "section": ObjType("config section", "section"),
    }
    directives = {"option": ConfigOption, "section": ConfigSection}
    roles = {"option": ConfigOptionXRefRole(), "section": ConfigSectionXRefRole()}

    initial_data = {"objects": {}}  # (type, name) -> docname, labelid

    def clear_doc(self, docname):
        toremove = []
        for key, (fn, _) in self.data["objects"].items():
            if fn == docname:
                toremove.append(key)
        for key in toremove:
            del self.data["objects"][key]

    def resolve_xref(self, env, fromdocname, builder, typ, target, node, contnode):
        docname, labelid = self.data["objects"].get((typ, target), ("", ""))
        if not docname:
            return None
        else:
            return make_refnode(builder, fromdocname, docname, labelid, contnode)

    def get_objects(self):
        for (type, name), info in self.data["objects"].items():
            yield (
                name,
                name,
                type,
                info[0],
                info[1],
                self.object_types[type].attrs["searchprio"],
            )


def autolink(urlpattern, textpattern="{}"):
    def role(name, rawtext, text, lineno, inliner, options={}, content=[]):
        url = urlpattern.format(text)
        xtext = textpattern.format(text)
        node = nodes.reference(rawtext, xtext, refuri=url, **options)
        return [node], []

    return role


def bcommand():
    def role(name, rawtext, text, lineno, inliner, options={}, content=[]):

        env = inliner.document.settings.env

        try:
            command, parameter = text.split(" ", 1)
        except ValueError:
            command = text
            parameter = ""

        indexstring = "Console; Command; {}".format(command)
        targetid = "bcommand-{}-{}".format(command, env.new_serialno("bcommand"))

        # Generic index entries
        indexnode = addnodes.index()
        indexnode["entries"] = []

        indexnode["entries"].append(["single", indexstring, targetid, "", None])

        targetnode = nodes.target("", "", ids=[targetid])

        text_node = nodes.strong(text="{}".format(text))

        return [targetnode, text_node, indexnode], []

    return role


def os():

    # \newcommand{\os}[2]{\ifthenelse{\isempty{#2}}{%
    # \path|#1|\index[general]{Platform!#1}%
    # }{%
    # \path|#1 #2|\index[general]{Platform!#1!#2}%
    # }}

    def role(name, rawtext, text, lineno, inliner, options={}, content=[]):

        env = inliner.document.settings.env

        # Generic index entries
        indexnode = addnodes.index()
        indexnode["entries"] = []

        try:
            platform, version = text.split(" ", 1)
            targetid = "os-{}-{}-{}".format(platform, version, env.new_serialno("os"))
            indexnode["entries"].append(
                [
                    "single",
                    "Platform; {}; {}".format(platform, version),
                    targetid,
                    "",
                    None,
                ]
            )
        except ValueError:
            platform = text
            version = ""
            targetid = "os-{}-{}-{}".format(platform, version, env.new_serialno("os"))
            indexnode["entries"].append(
                ["single", "Platform; {}".format(platform), targetid, "", None]
            )

        targetnode = nodes.target("", "", ids=[targetid])

        text_node = nodes.strong(text="{}".format(text))

        return [targetnode, text_node, indexnode], []

    return role


def sinceVersion():
    def role(name, rawtext, text, lineno, inliner, options={}, content=[]):
        # version = self.arguments[0]
        # summary = self.arguments[1]
        version, summary = text.split(":", 1)
        summary = summary.strip()

        indexstring = "bareos-{}; {}".format(version, summary)
        idstring = "bareos-{}-{}".format(version, summary)
        _id = nodes.make_id(idstring)

        # Generic index entries
        indexnode = addnodes.index()
        indexnode["entries"] = []

        indexnode["entries"].append(["pair", indexstring, _id, "", None])

        targetnode = nodes.target("", "", ids=[_id])

        # text_node = nodes.Text(text='Version >= {}'.format(version))
        # text_node = nodes.strong(text='Version >= {}'.format(version))
        text_node = nodes.emphasis(text="Version >= {}".format(version))
        # target does not work with generated.
        # text_node = nodes.generated(text='Version >= {}'.format(version))

        return [targetnode, text_node, indexnode], []

    return role


def setup(app):
    app.add_domain(ConfigFileDomain)
    app.add_role("bcommand", bcommand())
    app.add_role("os", os())
    app.add_role("sinceversion", sinceVersion())
    app.add_role(
        "mantis", autolink("https://bugs.bareos.org/view.php?id={}", "Issue #{}")
    )

    # identifies the version of our extension
    return {"version": "0.4"}
