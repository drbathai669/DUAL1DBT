#!/usr/bin/env python3
"""
Optimized High Performance Proxy Server
Tối ưu đặc biệt cho pattern: connect -> request -> wait 10s -> disconnect
Xử lý nhiều trình duyệt với hiệu suất cao
"""

import socket
import threading
import select
import time
import logging
from urllib.parse import urlparse
import sys
from concurrent.futures import ThreadPoolExecutor
import queue
import gc
import signal
import platform

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('proxy.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class OptimizedProxy:
    def __init__(self, host='0.0.0.0', port=8888, max_workers=500, buffer_size=16384):
        self.host = host
        self.port = port
        self.max_workers = max_workers
        self.buffer_size = buffer_size
        self.running = False

        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="ProxyWorker"
        )

        self.connection_pool = queue.Queue(maxsize=100)

        self.stats = {
            'total_requests': 0,
            'active_connections': 0,
            'errors': 0,
            'peak_connections': 0,
            'avg_request_time': 0,
            'total_request_time': 0
        }

        self.stats_lock = threading.Lock()
        self.cleanup_interval = 30

    def start(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Chỉ dùng SO_REUSEPORT nếu là Linux
            if platform.system() != 'Windows':
                self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
            self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(2000)

            self.running = True
            logging.info(f"Optimized Proxy đang chạy tại {self.host}:{self.port}")
            logging.info(f"Max workers: {self.max_workers}, Buffer: {self.buffer_size}")

            threading.Thread(target=self.print_stats, daemon=True).start()
            threading.Thread(target=self.cleanup_resources, daemon=True).start()

            signal.signal(signal.SIGINT, self.signal_handler)
            signal.signal(signal.SIGTERM, self.signal_handler)

            while self.running:
                try:
                    client_socket, addr = self.server_socket.accept()
                    client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

                    self.executor.submit(self.handle_client, client_socket, addr)
                except Exception as e:
                    if self.running:
                        logging.error(f"Accept error: {e}")
                        time.sleep(0.1)
        except Exception as e:
            logging.error(f"Server startup error: {e}")
            self.stop()

    def handle_client(self, client_socket, addr):
        start_time = time.time()
        try:
            with self.stats_lock:
                self.stats['active_connections'] += 1
                if self.stats['active_connections'] > self.stats['peak_connections']:
                    self.stats['peak_connections'] = self.stats['active_connections']

            client_socket.settimeout(15)

            try:
                request = client_socket.recv(self.buffer_size).decode('utf-8', errors='ignore')
            except socket.timeout:
                return

            if not request:
                return

            with self.stats_lock:
                self.stats['total_requests'] += 1

            lines = request.split('\r\n')
            if not lines:
                return

            first_line = lines[0]
            if not first_line:
                return

            try:
                method, url, _ = first_line.split(' ', 2)
            except ValueError:
                return

            if method == 'CONNECT':
                self.handle_https_optimized(client_socket, url)
            else:
                self.handle_http_optimized(client_socket, request, url)

        except Exception as e:
            logging.error(f"Client {addr} error: {e}")
            with self.stats_lock:
                self.stats['errors'] += 1
        finally:
            try:
                client_socket.close()
            except:
                pass

            with self.stats_lock:
                self.stats['active_connections'] -= 1
                request_time = time.time() - start_time
                self.stats['total_request_time'] += request_time
                if self.stats['total_requests'] > 0:
                    self.stats['avg_request_time'] = (
                        self.stats['total_request_time'] / self.stats['total_requests']
                    )

    def handle_http_optimized(self, client_socket, request, url):
        server_socket = None
        try:
            if url.startswith('http://'):
                parsed = urlparse(url)
                host = parsed.hostname
                port = parsed.port or 80
            else:
                host_header = None
                for line in request.split('\r\n')[1:]:
                    if line.lower().startswith('host:'):
                        host_header = line.split(':', 1)[1].strip()
                        break

                if not host_header:
                    raise Exception("No host header found")

                if ':' in host_header:
                    host, port_str = host_header.split(':', 1)
                    port = int(port_str)
                else:
                    host = host_header
                    port = 80

            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.settimeout(5)
            server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            server_socket.connect((host, port))

            server_socket.send(request.encode('utf-8'))

            server_socket.settimeout(20)
            client_socket.settimeout(20)

            self.relay_data_optimized(client_socket, server_socket)

        except Exception as e:
            logging.debug(f"HTTP error: {e}")
            try:
                client_socket.send(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            except:
                pass
        finally:
            if server_socket:
                try:
                    server_socket.close()
                except:
                    pass

    def handle_https_optimized(self, client_socket, url):
        server_socket = None
        try:
            host, port = url.split(':')
            port = int(port)

            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.settimeout(5)
            server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            server_socket.connect((host, port))

            client_socket.send(b"HTTP/1.1 200 Connection Established\r\n\r\n")

            server_socket.settimeout(20)
            client_socket.settimeout(20)

            self.relay_data_optimized(client_socket, server_socket)

        except Exception as e:
            logging.debug(f"HTTPS error: {e}")
            try:
                client_socket.send(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            except:
                pass
        finally:
            if server_socket:
                try:
                    server_socket.close()
                except:
                    pass

    def relay_data_optimized(self, client_socket, server_socket):
        try:
            sockets = [client_socket, server_socket]
            while True:
                ready_sockets, _, error_sockets = select.select(sockets, [], sockets, 0.5)

                if error_sockets:
                    break

                if not ready_sockets:
                    try:
                        client_socket.send(b'', socket.MSG_DONTWAIT)
                        server_socket.send(b'', socket.MSG_DONTWAIT)
                    except:
                        break
                    continue

                for sock in ready_sockets:
                    try:
                        data = sock.recv(self.buffer_size)
                        if not data:
                            return
                        if sock is client_socket:
                            server_socket.send(data)
                        else:
                            client_socket.send(data)
                    except:
                        return
        except Exception as e:
            logging.debug(f"Relay ended: {e}")

    def cleanup_resources(self):
        while self.running:
            time.sleep(self.cleanup_interval)
            try:
                collected = gc.collect()
                if collected > 0:
                    logging.debug(f"Garbage collected: {collected} objects")
            except Exception as e:
                logging.error(f"Cleanup error: {e}")

    def print_stats(self):
        while self.running:
            time.sleep(30)
            with self.stats_lock:
                stats_copy = self.stats.copy()

            logging.info("=== PROXY STATS ===")
            logging.info(f"Total requests: {stats_copy['total_requests']}")
            logging.info(f"Active connections: {stats_copy['active_connections']}")
            logging.info(f"Peak connections: {stats_copy['peak_connections']}")
            logging.info(f"Errors: {stats_copy['errors']}")
            logging.info(f"Avg request time: {stats_copy['avg_request_time']:.2f}s")

            if stats_copy['total_requests'] > 0:
                success_rate = ((stats_copy['total_requests'] - stats_copy['errors']) /
                                stats_copy['total_requests']) * 100
                logging.info(f"Success rate: {success_rate:.1f}%")
            logging.info("=" * 20)

    def signal_handler(self, signum, frame):
        logging.info(f"Received signal {signum}")
        self.stop()

    def stop(self):
        logging.info("Stopping proxy server...")
        self.running = False
        try:
            self.server_socket.close()
        except:
            pass
        self.executor.shutdown(wait=False)
        logging.info("Proxy server stopped")


if __name__ == "__main__":
    PROXY_HOST = '0.0.0.0'
    PROXY_PORT = 8888
    MAX_WORKERS = 1000
    BUFFER_SIZE = 32768

    proxy = OptimizedProxy(
        host=PROXY_HOST,
        port=PROXY_PORT,
        max_workers=MAX_WORKERS,
        buffer_size=BUFFER_SIZE
    )

    try:
        proxy.start()
    except KeyboardInterrupt:
        print("\nShutting down proxy server...")
        proxy.stop()
        sys.exit(0)
