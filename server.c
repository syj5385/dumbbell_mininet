
/*
 * Implemented 2019. 07. 29
 *
 */
 
 
#include <stdio.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>
#include <string.h>
#include <fcntl.h>
#include <time.h>
#include <signal.h>


u_long totalLength = 0; 
u_long intervalLength = 0; 
long startTime = 0; 
long currentTime = 0;
long startInterval = 0;
int count = 0; 
int running = 0;
int sock = 0; 
int interval = 0; 

struct timeval startT; 
struct timeval val,gap;

void getdoubledt(char *dt){

    struct tm *ptm; 

    gettimeofday(&val, NULL);
    gap.tv_sec = val.tv_sec - startT.tv_sec; 
    gap.tv_usec = val.tv_usec - startT.tv_usec; 
    if(gap.tv_usec < 0){
        gap.tv_sec = gap.tv_sec -1; 
        gap.tv_usec = gap.tv_usec + 1000000;
    }

    sprintf(dt, "%ld.%06ld", gap.tv_sec, gap.tv_usec);

}

void timer(){
    char time_buf[50];
    char buf[100]; 

    bzero(time_buf,50);
    bzero(buf, 100);
    double goodput = intervalLength * 8000 / interval;
    //sprintf(buf,"[%.1f - %.1f] %0.2f %ld %ld\n",count *interval/1000.0, ((count+1)*interval/1000.0), goodput, intervalLength, totalLength); 

    getdoubledt(time_buf);

    sprintf(buf, "%s; %0.2f\n", time_buf, goodput);
    write(sock,buf, strlen(buf));
    //write(0, buf, strlen(buf));
    intervalLength = 0; 
    count++;
}


int createTimer(timer_t *timerID, int sec, int msec){
    struct sigevent te; 
    struct itimerspec its;
    struct sigaction sa; 
    int sigNO = SIGRTMIN;

    sa.sa_flags = SA_SIGINFO;
    sa.sa_sigaction = timer;
    sigemptyset(&sa.sa_mask);

    if(sigaction(sigNO, &sa, NULL) == -1){
        printf("Sigaction error\n");
        return -1; 
    }
    te.sigev_notify = SIGEV_SIGNAL;
    te.sigev_signo = sigNO;
    te.sigev_value.sival_ptr = timerID;
    timer_create(CLOCK_REALTIME, &te, timerID);

    its.it_interval.tv_sec = sec;
    its.it_interval.tv_nsec = msec * 1000000;

    its.it_value.tv_sec = sec; 
    its.it_value.tv_nsec = msec * 1000000;
    timer_settime(*timerID, 0, &its, NULL);

    return 0; 


}


int main(int argc, char** argv){

    struct sockaddr_in serveraddr; 
    struct sockaddr_in clientaddr; 
    int server_fd;
    int client_fd; 
    int client_len;
    uint8_t buf[100];
    int n; 
    double duration = 0.0; 
    float goodput = 0.0f; 

    interval = atoi(argv[3]);

    gettimeofday(&startT, NULL);

    sock = open(argv[2], O_WRONLY|O_CREAT,0644);

    timer_t timerID; 

    if(sock < 0)
        return 1;



    if(argc != 4){
        perror("Error : Failed to set argument");
        return 1;
    }
       

    if((server_fd = socket(AF_INET,SOCK_STREAM, 0)) == -1){
        perror("Error : Failed to open the server socket");
        return 1;
    }

    serveraddr.sin_family = AF_INET;
    serveraddr.sin_addr.s_addr = htons(INADDR_ANY);
    serveraddr.sin_port = htons(atoi(argv[1]));

    if(bind(server_fd, (struct sockaddr*)&serveraddr, sizeof(serveraddr)) == -1){
        perror("Error : Failed to bind port");
        return 1;
    }
    printf("Binding Socket\n");
    if(listen(server_fd, 1) == -1){

        perror("Error : Faled to listen client");
        return 1;
    }

    client_len = sizeof(clientaddr);
    client_fd = accept(server_fd, (struct sockaddr*)&clientaddr, &client_len);


    if(client_fd == -1){
        perror("Failed to accept TCP client");
        return 1;
    }
    printf("Accepted\n");

    //pthread_create(&resultThread, NULL, resulting, NULL);
    //pthread_detach(resultThread);
    
    createTimer(&timerID, 0, interval);
    timer();
    while(1){
        uint8_t buf_d[BUFSIZ];
        bzero(buf,100);
        n = read(client_fd, buf_d, BUFSIZ);
        if(n == -1){
            totalLength += 0 ;
            intervalLength += 0;
            continue; 

        }
        if(n == 0){
            currentTime = clock();
            break; 
        }
           
        totalLength += n; 
        intervalLength += n;

    }
    running = 0; 
    sleep(1);
    bzero(buf,100);
    sprintf(buf, "%ld.%06ld", gap.tv_sec, gap.tv_usec);
    duration = atof(buf);
    goodput = totalLength * 8 / duration;
    bzero(buf,100);
    sprintf(buf,"Total; %0.2f", goodput);
    //sprintf(buf,"-->>[ 0 - %0.1f ] %0.2f %ld\n", (count*interval/1000.0), goodput,  totalLength);
    write(sock, buf, strlen(buf));
    close(sock);

    return 0;
}

