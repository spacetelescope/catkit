// MCLS_Demo.cpp : Defines the entry point for the console application.
//

//#include "stdafx.h"
#include "MCLS1_Api.h"
#define MAXLEN 255

//CPL:
#include <stdio.h>
#include <iostream>
#include <tchar.h>
#include <string>


int SetChannel(int hdl, int channel)
{
    fnMCLS1_DLL_SetActiveChannel(hdl, channel);
    printf("Setting channel %d.\n", channel);
    return fnMCLS1_DLL_SetEnable(hdl, 1);
}

int SetCurrent(int hdl, float current)
{
    fnMCLS1_DLL_SetCurrent(hdl, current);
    printf("Setting current to %5.2f mA.\n", current);
    return fnMCLS1_DLL_SetCurrent(hdl, current);
}






int _tmain(int argc, _TCHAR* argv[])
{	
    std::string str="";
    int ret = 0;
    int channel;
    float current;

    if(argc != 3)
    {
        printf("Using default channel/current.\n");
        channel = 3;
        current = 50.0;
    }
    else if(argc==3)
    {
        channel = atoi(argv[1]);
        current = atof(argv[2]);
    }


	if(init_MCLS1()!= 0)
	{
        printf_s("Loading uart_library.dll failes. Check paths.\n");
		return 0;
	}
	char c[MAXLEN] = {0};
    fnMCLS1_DLL_List(c, MAXLEN);
    //printf_s("COM port : %s.\n", c);

    //int hdl = fnMCLS1_DLL_Open(c);
    //CPL:
    int hdl = fnMCLS1_DLL_Open("COM3");
	if(hdl < 0 ) 
	{ 
        printf_s("COM port failed. Check the driver installed correctly.\n");
		return 0;
	}


    // 1- Set Active Channel
    ret = SetChannel(hdl, channel);


    while(str != "quit" && str != "Quit" && str != "QUIT")
    {
        if(str!="") current = stof(str);
        // 2- Set Current of active channel
        ret = SetCurrent(hdl, current);

        //printf("Set Current (or Quit):\n");
        std::cin >> str;
    }


    printf("Quitting Laser Source\n");
    //CPL: disable current active channel:
    fnMCLS1_DLL_SetEnable(hdl, 0);

    //CPL: close port:
	fnMCLS1_DLL_Close(hdl);
	return 0;

}

