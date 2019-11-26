import socket
import time
import sys

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(("",5000))
server_socket.listen(5)

print("TCP server waiting for client on port 5000")

client_socket, address = server_socket.accept()
print('Connected to client -> ',address);

interval = 0.5
totalLength=0
interPrevLength=0
interLength=0
prev_t = time.time()
current_t = 0
inter_Goodput=0
total_Goodput=0
count=0



    
while 1:
    data = client_socket.recv(66535)
    totalLength += len(data)
    interLength += len(data)
    if not data:
        client_socket.close()
        server_socket.close()
        break; 

    current_t = time.time()
    if time.time() - prev_t >= interval:
        inter_Goodput=interLength / interval
        prev_t = current_t
        interLength=0
        inter_Goodput = inter_Goodput * 8.0 / 1000000.0
        print(str(count * interval) + " - " +str((count+1) * interval) + " : " + str(inter_Goodput) + " Mbps\n" )
        count = count+1
      





