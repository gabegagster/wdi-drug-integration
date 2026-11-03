"""Build readable MapForce UDFs and mechanically refactor the EMA/DPD diagrams.

Run from the repo root:
    python src/mapforce/helpers/build_mapping_functions.py
    python src/mapforce/helpers/build_mapping_functions.py --refactor

The first command only regenerates wdi_mapping_functions.mfd. --refactor also
rebuilds the main diagrams, preserving their CSV definitions and XML targets.
No datasets, exported XML, or existing low-level lookup functions are modified.
Python is a development tool here, not a dependency of MapForce execution.
"""

import argparse
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
MAPFORCE = HERE.parent
LIBRARY = HERE / "wdi_mapping_functions.mfd"
FUNCTION_IDS = {
    "makeMedicineId": 1200,
    "getActiveSubstances": 1210,
    "yesNoToBoolean": 1220,
    "parseAuthorisationDate": 1230,
    "splitStrengths": 1240,
    "standardizeRegulatoryStatus": 1250,
    "standardizeProductClass": 1260,
    "standardizeAtcCodes": 1270,
    "standardizeDosageForms": 1280,
    "standardizeRoutes": 1290,
}


def node(parent, tag, **attrs):
    return ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})


def header(root):
    node(node(node(root, "header"), "namespaces"), "namespace")


def write_xml(root, path):
    ET.indent(root, space="\t")
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        ET.ElementTree(root).write(stream, encoding="unicode", xml_declaration=True)
        stream.write("\n")


def blank_mapping():
    root = ET.Element("mapping", version="35")
    node(root, "resources")
    graph = Graph(node(root, "component", name="defaultmap", uid=1))
    return root, graph


class Graph:
    def __init__(self, component, uid_start=3000, key_start=300):
        self.component = component
        node(component, "properties", SelectedLanguage="builtin")
        self.children = node(node(component, "structure"), "children")
        self.connections = node(component, "connections")
        self.uid_counter = uid_start
        self.key_counter = key_start
        self.input_parameters = []
        self.output_parameters = []

    def uid(self):
        self.uid_counter += 1
        return self.uid_counter

    def key(self):
        self.key_counter += 1
        return self.key_counter

    def connect(self, start, end):
        node(self.connections, "edge", **{"from": start, "to": end})

    def component_node(self, name, kind, x=420, y=0, library="core", uid=None, **attrs):
        c = node(self.children, "component", name=name, library=library,
                 uid=uid if uid is not None else self.uid(), kind=kind, **attrs)
        node(c, "view", ltx=x, lty=y, rbx=x + max(150, len(name) * 8), rby=y + 70)
        return c

    def parameter(self, name, kind, datatype="string", optional=False, sequence=False):
        uid = self.uid()
        c = self.component_node(name, kind, uid=uid, x=20 if kind == 6 else 1200,
                                y=100 * len(self.input_parameters))
        port = node(c, "targets" if kind == 6 else "sources")
        key = self.key()
        node(port, "datapoint", pos=0, key=key)
        data = node(c, "data")
        node(data, "input" if kind == 6 else "output", datatype=datatype)
        attrs = {"usageKind": "input" if kind == 6 else "output", "name": name}
        if optional:
            attrs["optional"] = "1"
        if sequence:
            attrs["sequence"] = "1"
        node(data, "parameter", **attrs)
        record = (name, uid, key)
        (self.input_parameters if kind == 6 else self.output_parameters).append(record)
        return key

    def output(self, start, name="result", datatype="string", sequence=False):
        key = self.parameter(name, 7, datatype, sequence=sequence)
        self.connect(start, key)

    def constant(self, value, datatype="string", x=220, y=0):
        c = self.component_node("constant", 2, x=x, y=y)
        key = self.key()
        node(node(c, "targets"), "datapoint", pos=0, key=key)
        node(node(c, "data"), "constant", value=value, datatype=datatype)
        return key

    def function(self, name, args, x=420, y=0):
        attrs = {"growable": "1", "growablebasename": "value"} if name == "concat" else {}
        c = self.component_node(name, 5, x=x, y=y, **attrs)
        inputs = node(c, "sources")
        for pos, source in enumerate(args):
            if source is None:
                node(inputs, "datapoint")
            else:
                key = self.key()
                node(inputs, "datapoint", pos=pos, key=key)
                self.connect(source, key)
        result = self.key()
        node(node(c, "targets"), "datapoint", pos=0, key=result)
        return result

    def filter(self, value, condition, x=700, y=0):
        c = self.component_node("filter", 3, x=x, y=y)
        inputs = node(c, "sources")
        for pos, source in enumerate((value, condition)):
            key = self.key()
            node(inputs, "datapoint", pos=pos, key=key)
            self.connect(source, key)
        result = self.key()
        outputs = node(c, "targets")
        node(outputs, "datapoint", pos=0, key=result)
        node(outputs, "datapoint")
        return result

    def user_function(self, definition, args, x=420, y=0):
        c = self.component_node(definition.get("name"), 19, x=x, y=y,
                                library="user", visible="0")
        data = node(c, "data")
        input_root = node(data, "root")
        header(input_root)
        result = {}
        for p in definition.findall("./structure/children/component"):
            parameter = p.find("./data/parameter")
            if parameter is None:
                continue
            name = parameter.get("name")
            if parameter.get("usageKind") == "input":
                entry = node(input_root, "entry", name=name, componentid=p.get("uid"))
                source = args.get(name)
                if source is not None:
                    key = self.key()
                    entry.set("inpkey", str(key))
                    self.connect(source, key)
            else:
                root = node(data, "root")
                header(root)
                if p.get("library") == "xml":
                    # Structured calls wrap the schema tree in the parameter.
                    wrapper = node(root, "entry", name=name,
                                   componentid=p.get("uid"), expanded=1)
                    entry = deepcopy(p.find("./data/root/entry"))
                    wrapper.append(entry)
                    for e in entry.iter("entry"):
                        e.attrib.pop("inpkey", None)
                        key = self.key()
                        e.set("outkey", str(key))
                        result[e.get("name")] = key
                else:
                    key = self.key()
                    node(root, "entry", name=name, componentid=p.get("uid"), outkey=key)
                    result[name] = key
        return result


def new_udf(name, description):
    uid = FUNCTION_IDS[name]
    c = ET.Element("component", name=name, library="user", uid=str(uid),
                   inline="1", editable="1", blackbox="0")
    node(c, "description").text = description
    return Graph(c, uid_start=uid * 100, key_start=0)


def build_library(low_level):
    root, _ = blank_mapping()
    settings = ET.Element("settings")
    node(node(settings, "libraries"), "import", path="wdi_helpers.mfd", saverelative=1)
    root.insert(0, settings)
    definitions = {}

    def finish(g):
        root.append(g.component)
        definitions[g.component.get("name")] = g.component

    g = new_udf("makeMedicineId", "Prefix the source key with source and an underscore.")
    source = g.parameter("source", 6)
    key = g.parameter("key", 6)
    underscore = g.constant("_")
    g.output(g.function("concat", [source, underscore, key]))
    finish(g)

    g = new_udf("getActiveSubstances", "Prefer a nonblank primary value, otherwise fallback; split using the source separator.")
    primary = g.parameter("primary", 6, optional=True)
    fallback = g.parameter("fallback", 6, optional=True)
    separator = g.parameter("separator", 6)
    empty = g.constant("")
    values = []
    for i, value in enumerate((primary, fallback)):
        text = g.function("normalize-space", [value], x=250, y=i * 180)
        nonblank = g.function("not-equal", [text, empty], x=450, y=i * 180)
        values.append(g.filter(text, nonblank, x=650, y=i * 180))
    selected = g.function("substitute-missing", values, x=850)
    g.output(g.function("tokenize", [selected, separator], x=1050), sequence=True)
    finish(g)

    g = new_udf("yesNoToBoolean", 'Return true for "Yes" and false for any other present value.')
    value = g.parameter("value", 6)
    yes = g.constant("Yes")
    g.output(g.function("equal", [value, yes]), datatype="boolean")
    finish(g)

    g = new_udf("parseAuthorisationDate", "Parse an EMA DD/MM/YYYY date; absent input produces no date.")
    value = g.parameter("value", 6)
    picture = g.constant("[D01]/[M01]/[Y0001]", datatype="anySimpleType")
    g.output(g.function("parse-date", [value, picture, None]), datatype="date")
    finish(g)

    for name, original, description in (
        ("standardizeRegulatoryStatus", "stdRegulatoryStatus", "Standardize one regulatory status using the shared lookup."),
        ("standardizeProductClass", "stdProductClass", "Standardize product class using the shared precedence rules."),
        ("standardizeDosageForms", "dosageFormList", "Standardize, deduplicate and sort dosage forms."),
        ("standardizeRoutes", "routeList", "Standardize, deduplicate and sort administration routes."),
    ):
        g = new_udf(name, description)
        raw = g.parameter("raw", 6)
        result = g.user_function(low_level[original], {"raw": raw})["result"]
        g.output(result)
        finish(g)

    g = new_udf("standardizeAtcCodes", "Combine available human/veterinary code lists and standardize their ATC codes.")
    codes = g.parameter("codes", 6, optional=True)
    additional = g.parameter("additionalCodes", 6, optional=True)
    separator = g.constant(";")
    joined = g.function("concat", [codes, separator, additional])
    result = g.user_function(low_level["stdAtcCode"], {"raw": joined}, x=700)["result"]
    g.output(result)
    finish(g)

    g = new_udf("splitStrengths", "Split a DPD strength list into individual tokens; validate each using strengthValue.")
    raw = g.parameter("values", 6)
    separator = g.constant("; ")
    tokens = g.function("tokenize", [raw, separator], x=300)
    # Keep the large strength lookups in the caller: nesting them in a new UDF
    # causes the Built-in compiler to fail on the DPD mapping.
    g.output(tokens, sequence=True)
    finish(g)
    return root, definitions


def refactor_main(path, definitions, low_level, source_name):
    old = ET.parse(path).getroot()
    old_children = old.find("./component/structure/children")
    source = deepcopy(old_children.find("./component[@library='text']"))
    target = deepcopy(old_children.find("./component[@library='xml']"))
    # Preserve source and target definitions, including their existing port keys.
    source.find("view").attrib.update(ltx="20", lty="0", rbx="470", rby="700")
    target.find("view").attrib.update(ltx="1170", lty="0", rbx="1650", rby="750")
    root, g = blank_mapping()
    settings = ET.Element("settings")
    imports = node(settings, "libraries")
    for filename in ("wdi_helpers.mfd", "wdi_mapping_functions.mfd"):
        node(imports, "import", path=f"helpers\\{filename}", saverelative=1)
    root.insert(0, settings)
    g.children.extend((source, target))

    def call(name, args, y, x=650):
        return g.user_function(definitions[name], args, x=x, y=y)

    jurisdiction = g.constant(source_name, x=500, y=-70)
    separator = g.constant("; ", x=500, y=150)
    if source_name == "EMA":
        empty = g.constant("", x=500, y=240)
        rows, key, primary, fallback = 100, 103, 105, empty
        medicine, wrapper, substance, count = 200, 204, 205, 206
        id_target, source_target = 201, 202
    else:
        empty = g.constant("", x=500, y=240)
        rows, key, primary, fallback = 9, 10, 12, empty
        medicine, wrapper, substance, count = 16, None, 20, 44
        id_target, source_target = 17, 18
    id_value = call("makeMedicineId", {"source": jurisdiction, "key": key}, 0)["result"]
    g.connect(id_value, id_target)
    g.connect(jurisdiction, source_target)
    substances = call("getActiveSubstances", {"primary": primary, "fallback": fallback,
                                             "separator": separator}, 120)["result"]
    g.connect(substances, substance)
    n_substances = g.function("count", [rows, substances], x=900, y=160)
    g.connect(n_substances, count)
    selected_rows = rows
    if source_name == "EMA":
        has_substances = g.function("exists", [substances], x=900, y=260)
        selected_rows = g.filter(rows, has_substances, x=900, y=350)
        g.connect(selected_rows, wrapper)
    g.connect(selected_rows, medicine)

    if source_name == "EMA":
        g.connect(102, 203)
        g.connect(111, 207)
        status = call("standardizeRegulatoryStatus", {"raw": 104}, 430)["result"]
        g.connect(status, 208)
        g.connect(call("standardizeProductClass", {"raw": 101}, 530)["result"], 209)
        atc = g.user_function(low_level["stdAtcCode"], {"raw": 106}, x=650, y=630)["result"]
        g.connect(atc, 210)
        for i, (field, destination) in enumerate(((109, 211), (108, 212), (110, 213))):
            g.connect(call("yesNoToBoolean", {"value": field}, 740 + i * 100)["result"], destination)
        g.connect(call("parseAuthorisationDate", {"value": 112}, 1040)["result"], 214)
    else:
        g.connect(11, 19)
        g.connect(13, 21)
        status = g.user_function(low_level["bestRegulatoryStatus"], {"raw": 38}, x=650, y=300)["result"]
        g.connect(status, 29)
        g.connect(g.user_function(low_level["stdProductClass"], {"raw": 36}, x=650, y=400)["result"], 30)
        g.connect(g.user_function(low_level["stdAtcCode"], {"raw": 37}, x=650, y=500)["result"], 31)
        g.connect(call("yesNoToBoolean", {"value": 14}, 600)["result"], 22)
        g.connect(g.user_function(low_level["dosageFormList"], {"raw": 45}, x=650, y=700)["result"], 48)
        g.connect(g.user_function(low_level["routeList"], {"raw": 49}, x=650, y=800)["result"], 52)
        tokens = call("splitStrengths", {"values": 53}, 900)["result"]
        numeric = g.user_function(low_level["strengthValue"], {"raw": tokens}, x=850, y=1000)["result"]
        supported = g.function("exists", [numeric], x=1050, y=1000)
        strengths = g.filter(tokens, supported, x=850, y=1100)
        g.connect(strengths, 66)
        for name, destination, y in (("strengthValue", 67, 900), ("strengthUnit", 68, 1000)):
            result = g.user_function(low_level[name], {"raw": strengths}, x=900, y=y)["result"]
            g.connect(result, destination)
        strength_count = g.function("count", [rows, strengths], x=900, y=1200)
        zero = g.constant("0", datatype="integer", x=700, y=1200)
        has_strengths = g.function("greater", [strength_count, zero], x=1100, y=1200)
        strength_rows = g.filter(rows, has_strengths, x=900, y=1050)
        g.connect(strength_rows, 71)
        g.connect(15, 23)
    return root


def validate_graph(root):
    for definition in root.findall("component"):
        children = definition.findall("./structure/children/component")
        ids = [c.get("uid") for c in children]
        assert len(ids) == len(set(ids)), (definition.get("name"), "duplicate component IDs")
        keys, incoming, outgoing = [], set(), set()
        for c in children:
            for e in c.iter():
                keys.extend(v for k, v in e.attrib.items() if k in ("key", "inpkey", "outkey"))
            incoming.update(e.get("key") for e in c.findall("./sources/datapoint") if e.get("key"))
            outgoing.update(e.get("key") for e in c.findall("./targets/datapoint") if e.get("key"))
            incoming.update(e.get("inpkey") for e in c.findall(".//entry") if e.get("inpkey"))
            outgoing.update(e.get("outkey") for e in c.findall(".//entry") if e.get("outkey"))
        assert len(keys) == len(set(keys)), (definition.get("name"), "duplicate port keys")
        destinations = []
        for edge in definition.findall("./connections/edge"):
            assert edge.get("from") in outgoing and edge.get("to") in incoming, edge.attrib
            destinations.append(edge.get("to"))
        assert len(destinations) == len(set(destinations)), "Multiple connections into one input"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refactor", action="store_true")
    args = parser.parse_args()
    low_level = {c.get("name"): c for c in ET.parse(HERE / "wdi_helpers.mfd").getroot().findall("component")
                 if c.get("library") == "user"}
    library, definitions = build_library(low_level)
    validate_graph(library)
    write_xml(library, LIBRARY)
    print(f"Built {len(definitions)} named UDFs: {LIBRARY.name}")
    if args.refactor:
        for source in ("ema", "dpd"):
            path = MAPFORCE / f"{source}_mapping.mfd"
            root = refactor_main(path, definitions, low_level, source.upper())
            validate_graph(root)
            write_xml(root, path)
            print(f"Refactored {path.name}: {len(root.findall('./component/structure/children/component'))} components")


if __name__ == "__main__":
    main()
