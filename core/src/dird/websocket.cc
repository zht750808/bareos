/*
   BAREOS® - Backup Archiving REcovery Open Sourced

   Copyright (C) 2019-2019 Bareos GmbH & Co. KG

   This program is Free Software; you can redistribute it and/or
   modify it under the terms of version three of the GNU Affero General Public
   License as published by the Free Software Foundation and included
   in the file LICENSE.

   This program is distributed in the hope that it will be useful, but
   WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
   Affero General Public License for more details.

   You should have received a copy of the GNU Affero General Public License
   along with this program; if not, write to the Free Software
   Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
   02110-1301, USA.
*/

#include "include/bareos.h"
#include "websocket.h"
#include "dird/websocketserver.h"
#include "seasocks/Server.h"

#include "dird/ua_server.h"

extern std::unique_ptr<directordaemon::WebsocketServer> websocketserver;

namespace directordaemon {


void WebsocketHandler::onConnect(seasocks::WebSocket* con)
{
  BareosWebsocket *bws = new BareosWebsocket(con);
  bws->webs_conn = con;
  UaWebsocketThread *bwst = new UaWebsocketThread(bws);
  connections_map_.insert({con, bwst});
}

void WebsocketHandler::onDisconnect(seasocks::WebSocket* con) { connections_map_.erase(con); }

void WebsocketHandler::onData(seasocks::WebSocket* con, const char* data)
{
  auto it = connections_map_.find(con);
  if (it == connections_map_.end()) { return; }
  UaWebsocketThread* bwst = connections_map_.at(con);
  bwst->bws_->read_nbytes(const_cast<char*>(data), strlen(data) +1);
}

void WebsocketHandler::onData(seasocks::WebSocket* con, const uint8_t* data, size_t size)
{
  auto it = connections_map_.find(con);
  if (it == connections_map_.end()) { return; }
  UaWebsocketThread* bwst = connections_map_.at(con);
  memcpy(bwst->bws_->msg, data, size);
}

BareosWebsocket::BareosWebsocket(seasocks::WebSocket* websocket)
  : websocket_(websocket)
  , bytes_available_(0)
{
  return;
}

int32_t BareosWebsocket::read_nbytes(char *ptr, int32_t nbytes)
{
  strncpy(msg, ptr, nbytes);
  bytes_available_.store(nbytes);
  return nbytes;
}

int32_t BareosWebsocket::recv()
{
  uint32_t bytes_available = bytes_available_.load();
  while (!bytes_available) {
    Bmicrosleep(0,1000);
    bytes_available = bytes_available_.load();
  }
  bytes_available_.store(0);
  return bytes_available;
}

static char message[4096];
static std::atomic<uint32_t> length(0);
static seasocks::WebSocket *websocket = nullptr;

static void send_in_websockets_thread(void)
{
  if (websocket && length.load()) {
    std::string m(message);
    websocket->send(m);
    message[0] = 0;
    length.store(0);
  }
}

bool BareosWebsocket::send()
{
  if (websocket_ && message_length > 0) {
    websocket = websocket_;
    memcpy(message, msg, message_length +1);
    length.store(message_length +1);
    websocketserver->server_->execute(send_in_websockets_thread);
    while (length.load()) continue;
    return true;
  }
  return false;
}

UaWebsocketThread::UaWebsocketThread(BareosWebsocket *bws)
  : bws_(bws)
  , thread_(new std::thread(HandleUserAgentClientRequest, bws))
{

}

} /* namespace directordaemon */
