import xml.etree.ElementTree as et
from xml.etree.ElementTree import tostring as xml2str, indent
import xml.parsers.expat as expat
from xml.parsers.expat import XML_PARAM_ENTITY_PARSING_NEVER

def get_start_tag(e: et.Element):
    xml = xml2str(e).decode()
    ofs = xml.index("/>")
    xml = xml[0:ofs]
    return xml + ">"

def switch_direction(e: et.Element):
    _to = e.attrib.get("from")
    _from = e.attrib.get("to")

    if _to != None:
        del e.attrib["from"]

    if _from != None:
        del e.attrib["to"]

    if _to != None:
        e.attrib["to"] = _to

    if _from != None:
        e.attrib["from"] = _from

def to_xml_string(e: et.Element, indented=False):
    if indented:
        indent(e, space="  ")

    return xml2str(e, xml_declaration=False, short_empty_elements=True).decode("UTF-8")

class Jid:
    def __init__(self):
        self.local = None
        self.domain = None
        self.resource = None

    def __str__(self) -> str:
        s = ""

        if self.local != None:
            s += f"{self.local}@"

        if self.domain != None:
            s += self.domain

        if self.resource != None:
            s += f"/{self.resource}"

        return s

class XmppElement(et.Element):
    def __init__(self, tag: str, attrib: dict[str, str] = None) -> None:
        super().__init__(tag, attrib or {})
        self._parent = None

    def get_parent(self):
        return self._parent
    
    def set_parent(self, newParent):
        if self._parent != None:
            self._parent.remove(self)

        self._parent = newParent

        if newParent!=None:
            newParent.append(self)

class Parser:
    def __init__(self, session, encoding: str = None):
        self._session = session
        self._parser = expat.ParserCreate(encoding or "UTF-8")
        self._stack = []
        self.reset()
        self._current: XmppElement = None
        self.is_cdata = False

    def reset(self):
        def on_cdata_start():
            self.is_cdata = True
        
        def on_cdata_end():
            self.is_cdata = False

        def on_text(value):
            if not self.is_cdata:
                if self._current != None:
                    if self._current.text == None:
                        self._current.text = value
                    else:
                        self._current.text += value

        def on_element_start(name:str, attrs: dict[str, str]):
            el = XmppElement(name, attrs)
            
            if name == "stream:stream":
                self._session.handle_stream_start(el)
                return

            if self._current != None:
                el.set_parent(self._current)

            self._current = el

        def on_element_end(name: str):
            if name == "stream:stream":
                self._session.handle_stream_end()
            else:
                parent = self._current.get_parent()

                if parent == None:
                    self._session.handle_stream_element(self._current)

                self._current = parent
            
        
        self._parser.StartElementHandler = on_element_start
        self._parser.EndElementHandler = on_element_end
        self._parser.StartCdataSectionHandler = on_cdata_start
        self._parser.EndCdataSectionHandler = on_cdata_end
        self._parser.CharacterDataHandler = on_text
        self._parser.SetParamEntityParsing(XML_PARAM_ENTITY_PARSING_NEVER)
        
    def write(self, buf: str, isFinal = False) -> bool:
        return self._parser.Parse(buf, isFinal) > 0