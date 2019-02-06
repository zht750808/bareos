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

#include "seasocks/PageHandler.h"
#include "seasocks/PrintfLogger.h"
#include "seasocks/Server.h"
#include "seasocks/WebSocket.h"
#include "seasocks/StringUtil.h"

#include <memory>
#include <set>
#include <string>

// Simple chatroom server, showing how one might use authentication.

using namespace std;
using namespace seasocks;

namespace websocketserver {

struct Handler : WebSocket::Handler {
    set<WebSocket*> _cons;

    void onConnect(WebSocket* con) override {
        _cons.insert(con);
        send(con->credentials()->username + " has joined");
    }
    void onDisconnect(WebSocket* con) override {
        _cons.erase(con);
        send(con->credentials()->username + " has left");
    }

    void onData(WebSocket* con, const char* data) override {
        send(con->credentials()->username + ": " + data);
    }

    void send(const string& msg) {
        for (auto* con : _cons) {
            con->send(msg);
        }
    }
};

struct MyAuthHandler : PageHandler {
    shared_ptr<Response> handle(const Request& request) override {
        // Here one would handle one's authentication system, for example;
        // * check to see if the user has a trusted cookie: if so, accept it.
        // * if not, redirect to a login handler page, and await a redirection
        //   back here with relevant URL parameters indicating success. Then,
        //   set the cookie.
        // For this example, we set the user's authentication information purely
        // from their connection.
        request.credentials()->username = formatAddress(request.getRemoteAddress());
        return Response::unhandled(); // cause next handler to run
    }
};

void start_websocketserver()
{
    Server server(make_shared<PrintfLogger>());
    server.addPageHandler(make_shared<MyAuthHandler>());
    server.addWebSocketHandler("/chat", make_shared<Handler>());
    server.serve("/home/franku/01-prj/git/seasocks/src/ws_chatroom_web", 9000);
}

} /* websocketserver */
