from multiprocessing import Queue
from socket import socket,AF_INET,IPPROTO_TCP,SOCK_STREAM
from threading import Thread
from time import sleep
import xml.etree.ElementTree as et
from base64 import b64decode
from uuid import uuid4

from xmpp import Jid, Parser, XmppElement, get_start_tag, switch_direction, to_xml_string

class Session:
    def __init__(self, socket: socket, addr):
        self.session_id = uuid4()
        print(f"-- session opened: {self.session_id}")
        
        self._authenticated = False
        self._address = addr
        self._jid = Jid()
        self._jid.domain = "warface"

        self._isOpen = True
        self._readable = True
        self._writable = True

        self._socket = socket
        self._receiveThread = Thread(target=self._on_receive,daemon=True)
        self._sendThread = Thread(target=self._on_send,daemon=True)
        self._parser = Parser(self, "UTF-8")
        self._sendQueue = Queue()

    def start(self):
        self._sendThread.start()
        self._receiveThread.start()

    def stop(self):
        if not self._isOpen:
            return
    
        self._isOpen = False
        self._readable = False

        t = Thread(target=self._on_stop,daemon=True)
        t.start()

    def _on_stop(self):
        while not self._sendQueue.empty():
            sleep(0.1)

        self._writable = False

    def _on_receive(self):
        while self._isOpen:

            if not self._readable:
                sleep(0.1)
                continue

            buf = self._socket.recv(256)
            size = len(buf)

            if size <= 0:
                print("client closed")
                break

            if not self._parser.write(buf, False):
                print("parser error")
                break

    def _on_send(self):
        while self._writable != 0:
            item = self._sendQueue.get()
            self._socket.send(item)
            sleep(0.1)

    def handle_stream_start(self, e: et.Element):
        features = XmppElement("stream:features")

        if not self._authenticated:
            mechanisms = et.Element("mechanisms")
            
            m = et.Element("mechanism")
            m.text = "PLAIN"
            mechanisms.append(m)

            features.append(mechanisms)
        else:
            features.append(et.Element("bind", {"xmlns":"urn:ietf:params:xml:ns:xmpp-bind"}))
            features.append(et.Element("session", {"xmlns":"urn:ietf:params:xml:ns:xmpp-session"}))

        del e.attrib["to"]
        e.attrib["from"] = self._jid.domain
        self.send(get_start_tag(e))
        self.send(to_xml_string(features))

    def send(self, xml: bytes | str):
        s = None

        if isinstance(xml, et.Element):
            s = to_xml_string(xml)
            print(f"send >>\n{to_xml_string(xml, indented=True)}\n")
        else:
            s = str(xml)
            print(f"send >>\n{s}\n")

        self._sendQueue.put(bytes(s, "UTF-8"), False)

    def handle_stream_end(self):
        print(f"recv <<\n</stream:stream>\n")
        self.stop()
        pass

    def handle_stream_element(self, e: et.Element):
        print(f"recv <<\n{to_xml_string(e, indented=True)}\n")
        
        if e.tag == "auth":
            sasl = b64decode(bytes(e.text, "utf-8")).decode().split('\0')

            if len(sasl) == 3:
                user = sasl[1]
            else:
                user = sasl[0]

            self._jid.local = user

            self.send("<success xmlns='urn:ietf:params:xml:ns:xmpp-sasl' />")
            self._authenticated = True
        elif e.tag == "iq":
            query = e.find("./")

            if query.tag == "bind":
                e.attrib["type"] = "result"

                switch_direction(e)

                resource = query.find('./resource')
                self._jid.resource = resource.text or "GameClient"
                query.remove(resource)

                jid = et.Element("jid")
                jid.text = str(self._jid)
                query.append(jid)

                self.send(e)

            if query.tag == "session":
                e.attrib["type"] = "result"
                switch_direction(e)
                self.send(e)





server = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
server.bind(("0.0.0.0", 5222))
server.listen(10)

sessions: list[Session] = []

while True:
    sleep(0.1)

    client, addr = server.accept()

    if client == None:
        continue

    s = Session(client, addr)
    s.start()
    sessions.append(s)