#!/bin/bash

interval=$(echo "scale=1;$1/1000" | bc)
key=1
output=''
nc -l 5000 >./temp &
while [ $key -eq 1 ]
do 
    size=$(wc -c "./temp" | awk '{print $1}')
    if [ $size -ne 0 ]; then
        break
    fi
done

ncpid=$!
count=0
prevSize=0
startTime=$(date +%s)
intervalTime=0
intervalEndTime=0
zerocount=0
while [ $key -eq 1 ]
do   
    intervalTime=$(date +%s)
    sleep $interval
    intervalEndTime=$(date +%s)

    thisSize=$(wc -c "./temp" | awk '{print $1}')
    received=`expr $thisSize - $prevSize`
    prevSize=$((thisSize))
    receivedtoBit=`expr $received \* 8`
    goodput=$(echo "scale=2;$receivedtoBit*$1/10000000" | bc)
    #goodput=$(echo "$receivedtoBit")
    #echo "[$count - $((count+1))]  $goodput">>$2

    startT=$(echo "scale=1;$count*$1/1000" | bc)
    endT=$(echo "scale=1;$((count+1))*$1/1000" | bc)

#    echo "[$startT - $endT]  $goodput"
    printf "%0.1f - %0.1f   %0.2f Mbps\n" "$startT" "$endT" "$goodput" >> $2
    
    count=$((count+1))
    if [ $received -eq 0 ]; then
        break
    fi

done

totalSize=$(wc -c "./temp" | awk '{print $1}')
totalTime=$(echo "scale=1;$count*$1/1000" | bc)
totalgoodput=$(echo "scale=2;$totalSize*8/$totalTime/1000000" | bc)
printf "0 - %0.1f   %0.2f\n" "$totalTime" "$totalgoodput" >> $2

rm ./temp
#kill $ncpid


