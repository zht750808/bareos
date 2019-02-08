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

#ifndef BAREOS_DIRD_BAREOSWEBSOCKET_H_
#define BAREOS_DIRD_BAREOSWEBSOCKET_H_

#include "seasocks/WebSocket.h"

#include <queue>
#include <vector>
#include <atomic>
#include <thread>

namespace directordaemon {

class BareosWebsocket;
class UaWebsocketThread;

class WebsocketHandler : public seasocks::WebSocket::Handler {
 public:
  void onConnect(seasocks::WebSocket *con) override;
  void onDisconnect(seasocks::WebSocket *con) override;
  void onData(seasocks::WebSocket *con, const char *data) override;
  void onData(seasocks::WebSocket *con, const uint8_t *data, size_t size) override;

 private:
  std::map<seasocks::WebSocket *, UaWebsocketThread *> connections_map_;
};

class BareosWebsocket : public BareosSocket {
 private:
  seasocks::WebSocket *websocket_ = nullptr;
  std::atomic<int32_t> bytes_available_;

 public:
  BareosWebsocket(seasocks::WebSocket *websocket_);
  int32_t recv() override;
  bool send() override;

  void FinInit(JobControlRecord *jcr,
               int sockfd,
               const char *who,
               const char *host,
               int port,
               struct sockaddr *lclient_addr) override
  {
    return;
  }
  bool open(JobControlRecord *jcr,
            const char *name,
            const char *host,
            char *service,
            int port,
            utime_t heart_beat,
            int *fatal) override
  {
    return false;
  }

  BareosSocket *clone() override { return nullptr; };
  bool connect(JobControlRecord *jcr,
               int retry_interval,
               utime_t max_retry_time,
               utime_t heart_beat,
               const char *name,
               const char *host,
               char *service,
               int port,
               bool verbose) override
  {
    return false;
  }
  int32_t read_nbytes(char *ptr, int32_t nbytes) override;
  int32_t write_nbytes(char *ptr, int32_t nbytes) override { return 0; }
  void close() override { return; }
  void destroy() override { return; }
  int GetPeer(char *buf, socklen_t buflen) override { return 0; }
  bool SetBufferSize(uint32_t size, int rw) override { return false; }
  int SetNonblocking() override { return 0; }
  int SetBlocking() override { return 0; }
  void RestoreBlocking(int flags) override { return; }
  bool ConnectionReceivedTerminateSignal() override { return false; }
  /*
   * Returns: 1 if data available, 0 if timeout, -1 if error
   */
  int WaitData(int sec, int usec = 0) override { return 0; }
  int WaitDataIntr(int sec, int usec = 0) override { return 0; }
};

class UaWebsocketThread {
 public:
  UaWebsocketThread(BareosWebsocket *websocket);
  BareosWebsocket *bws_;

 private:
  std::shared_ptr<std::thread> thread_;
};

} /* namespace directordaemon */

#endif /* BAREOS_DIRD_BAREOSWEBSOCKET_H_ */
