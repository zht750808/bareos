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

#ifndef BAREOS_DIRD_WEBSOCKETSSERVER_H_
#define BAREOS_DIRD_WEBSOCKETSSERVER_H_

#include "seasocks/Server.h"

#include <memory>
#include <thread>

namespace directordaemon {

class WebsocketServer {
 public:
  explicit WebsocketServer();

  bool Start();
  void Stop();
  std::shared_ptr<seasocks::Server> server_;

 private:
  std::unique_ptr<std::thread> server_thread_;

  static void WebsocketServerThread(std::shared_ptr<seasocks::Server> server);
};

} /* namespace directordaemon */

#endif /* BAREOS_DIRD_WEBSOCKETSSERVER_H_ */
