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
        self.session_id = str(uuid4())
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

    def start(self, close_cb):
        self._close_cb = close_cb
        self._sendThread.start()
        self._receiveThread.start()

    def stop(self):
        if not self._isOpen:
            return
    
        self._isOpen = False
        self._readable = False

        t = Thread(target=self._on_stop,daemon=True)
        t.start()

        self._close_cb(self)

    def _on_stop(self):
        # Ensure all data is sent
        while not self._sendQueue.empty():
            sleep(0.5)

        self._writable = False
        self._socket.close()

    def _on_receive(self):
        try:
            while self._isOpen:

                if not self._readable:
                    sleep(0.1)
                    continue

                # Set default buffer size for parsing context
                buf = self._socket.recv(4096)
                size = len(buf)

                if size <= 0:
                    break

                if not self._parser.write(buf, False):
                    break
        except Exception as err:
            print(f"RECV failed:\n{err}\n")
        finally:
            # ensure we really closed the session
            self.stop()

    def _on_send(self):
        try:
            while self._writable != 0:
                item = self._sendQueue.get()
                self._socket.send(item)
                sleep(0.1)
        except Exception as err:
            print(f"SEND failed:\n{err}\n")
        finally:
            # ensure we really closed the session
            self.stop()

    def handle_stream_start(self, e: et.Element):
        features = XmppElement("stream:features")

        if not self._authenticated:
            mechanisms = et.Element("mechanisms")
            
            m = et.Element("mechanism")
            m.text = "PLAIN"
            mechanisms.append(m)

            features.append(mechanisms)
        else:
            if self._jid.resource == None:
                features.append(et.Element("bind", {"xmlns":"urn:ietf:params:xml:ns:xmpp-bind"}))

            features.append(et.Element("session", {"xmlns":"urn:ietf:params:xml:ns:xmpp-session"}))

        switch_direction(e)
        e.attrib["id"] = self.session_id
        e.attrib["from"] = self._jid.domain

        # Its okay to send stream header + features, reduces amount of calls to send data.
        self.send(get_start_tag(e) + to_xml_string(features))

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
        xml = "</stream:stream>"
        self.send(xml)
        print(f"recv <<\n{xml}\n")
        self.stop()
        pass

    def handle_stream_element(self, e: et.Element):
        print(f"recv <<\n{to_xml_string(e, indented=True)}\n")
        
        if e.tag == "auth":
            sasl = b64decode(bytes(e.text, "utf-8")).decode().split('\0')

            if len(sasl) == 3:
                user = sasl[1]
                pwd = sasl[2]
            else:
                user = sasl[0]
                pwd = sasl[1]

            # check user & pwd in DB
            self._jid.local = user

            self.send("<success xmlns='urn:ietf:params:xml:ns:xmpp-sasl' />")
            self._authenticated = True
        elif e.tag == "iq":
            query = e.find("./")

            if query.tag == "bind":
                e.attrib["type"] = "result"

                switch_direction(e)

                # TODO: Handle resource bind conflict?
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

def on_close_callback(s: Session):
    sessions.remove(s)

while True:
    sleep(0.1)

    client, addr = server.accept()

    if client == None:
        continue

    s = Session(client, addr)
    s.start(on_close_callback)
    sessions.append(s)