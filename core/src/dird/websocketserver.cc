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

#include "websocketserver.h"

#include "seasocks/PageHandler.h"
#include "seasocks/PrintfLogger.h"
#include "seasocks/Server.h"
#include "seasocks/WebSocket.h"
#include "seasocks/StringUtil.h"

#include <memory>
#include <set>
#include <string>
#include <thread>
#include <exception>

struct Handler : seasocks::WebSocket::Handler {
  std::set<seasocks::WebSocket*> _cons;

  void onConnect(seasocks::WebSocket* con) override
  {
    _cons.insert(con);
    send(con->credentials()->username + " has joined");
  }
  void onDisconnect(seasocks::WebSocket* con) override
  {
    _cons.erase(con);
    send(con->credentials()->username + " has left");
  }

  void onData(seasocks::WebSocket* con, const char* data) override { send(con->credentials()->username + ": " + data); }

  void send(const std::string& msg)
  {
    for (auto* con : _cons) { con->send(msg); }
  }
};

struct MyAuthHandler : seasocks::PageHandler {
  std::shared_ptr<seasocks::Response> handle(const seasocks::Request& request) override
  {
    // Here one would handle one's authentication system, for example;
    // * check to see if the user has a trusted cookie: if so, accept it.
    // * if not, redirect to a login handler page, and await a redirection
    //   back here with relevant URL parameters indicating success. Then,
    //   set the cookie.
    // For this example, we set the user's authentication information purely
    // from their connection.
    request.credentials()->username = seasocks::formatAddress(request.getRemoteAddress());
    return seasocks::Response::unhandled();  // cause next handler to run
  }
};

WebsocketServer::WebsocketServer()
  : server_(new seasocks::Server(std::make_shared<seasocks::PrintfLogger>()))
{
  return;
}

bool WebsocketServer::Start()
{
  try {
    server_thread_.reset(new std::thread(WebsocketServerThread, server_));
  }
  catch( const std::exception &e ) {
    std::cout << e.what() << std::endl;
    return false;
  }
  return true;
}

void WebsocketServer::Stop()
{
  if (server_thread_) {
    server_->terminate();
    server_thread_->join();
  }
}

void WebsocketServer::WebsocketServerThread(std::shared_ptr<seasocks::Server> s)
{
  s->addPageHandler(std::make_shared<MyAuthHandler>());
  s->addWebSocketHandler("/chat", std::make_shared<Handler>());
  s->serve("/home/franku/01-prj/git/seasocks/src/ws_chatroom_web", 9000);
}
