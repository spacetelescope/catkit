#//include"stdafx.h"
#include<assert.h>
#define WIN32_LEAN_AND_MEAN
#include<Windows.h>
#include"MCLS1_Api.h"
#define MAXLEN 255
#define WRITE_BUFFER_SIZE  32
#define TEMP_HI 30.0f
#define TEMP_LO 20.0f
#define UART_WIN32
typedef int 	(*fnUART_open)(char* port, int nBaud, int timeout);
typedef int 	(*fnUART_list)(char *nPort, int var);
typedef int 	(*fnUART_close)(int hdl);
typedef int 	(*fnUART_Set)(int hdl, char *c, int var);
typedef int 	(*fnUART_Get)(int hdl, char *c, char *d);

fnUART_open open;
fnUART_list list;
fnUART_close close;
fnUART_Set set;
fnUART_Get get;

//CPL:
#include <stdio.h>

int init_MCLS1()
{
    #ifdef UART_WIN32
        HMODULE dll_handle=LoadLibrary(TEXT("C:/Users/jost/Desktop/SourceLaser/uart_library_win32.dll"));
    #else
        HMODULE dll_handle=LoadLibrary(TEXT("C:/Users/jost/Desktop/SourceLaser/uart_library_win64.dll"));
    #endif

    if(!dll_handle)
           return -1;
    open=(fnUART_open)GetProcAddress(dll_handle,("fnUART_LIBRARY_open"));
    list=(fnUART_list)GetProcAddress(dll_handle, ("fnUART_LIBRARY_list"));
    close=(fnUART_close)GetProcAddress(dll_handle, ("fnUART_LIBRARY_close"));
    set=(fnUART_Set)GetProcAddress(dll_handle, ("fnUART_LIBRARY_Set"));
    get=(fnUART_Get)GetProcAddress(dll_handle, ("fnUART_LIBRARY_Get"));

    if(open == NULL || list == NULL || close == NULL || set == NULL|| get == NULL)
        return -2;
    return 0;
}

int fnMCLS1_DLL_List(char* port, int var)
{
	int ret = 0;
	char temp[MAXLEN] = {0};
    ret = list(temp, MAXLEN);
    sscanf_s(temp,"%[^,]", port, MAXLEN);
	return ret;
}

int fnMCLS1_DLL_Open(char* port)
{
	int hdl = open(port, CBR_115200, 3);
	return hdl;
}

int fnMCLS1_DLL_Close(int hdl)
{
	int ret = 0;
	ret = close(hdl);
	return ret;
}

int fnMCLS1_DLL_SetActiveChannel(int hdl, int n)
{
	assert(n >= 1 && n <= 4);
	int ret = 0;
    char cmd[WRITE_BUFFER_SIZE] = {0};
	sprintf_s(cmd, WRITE_BUFFER_SIZE, "channel=%d\r", n);
	ret = set(hdl, cmd, WRITE_BUFFER_SIZE);
	return ret;
}

int fnMCLS1_DLL_SetTargeTemperature(int hdl, float n)
{
	assert(n >= TEMP_LO && n <= TEMP_HI);
	int ret = 0;
	char cmd[WRITE_BUFFER_SIZE] = {0};
	sprintf_s(cmd, WRITE_BUFFER_SIZE, "target=%f\r", n);	
	ret = set(hdl, cmd, WRITE_BUFFER_SIZE);
	return ret;
}

int fnMCLS1_DLL_SetCurrent(int hdl, float n)
{
	int ret = 0;
	char cmd[WRITE_BUFFER_SIZE] = {0};
	sprintf_s(cmd, WRITE_BUFFER_SIZE, "current=%f\r", n);	
	ret = set(hdl, cmd, WRITE_BUFFER_SIZE);
	return ret;
}

int fnMCLS1_DLL_SetEnable(int hdl, int n)
{
	assert(n >= 0 && n <= 1);
	int ret = 0;
	char cmd[WRITE_BUFFER_SIZE] = {0};
	sprintf_s(cmd, WRITE_BUFFER_SIZE, "enable=%d\r", n);
	ret = set(hdl, cmd, WRITE_BUFFER_SIZE);
	return ret;
}

int fnMCLS1_DLL_SetSystemEnable(int hdl, int n)
{
	assert(n >= 0 && n <= 1);
	int ret = 0;
	char cmd[WRITE_BUFFER_SIZE] = {0};
	sprintf_s(cmd, WRITE_BUFFER_SIZE, "system=%d\r", n);
	ret = set(hdl, cmd, WRITE_BUFFER_SIZE);
	return ret;
}

int fnMCLS1_DLL_GetActiveChannel(int hdl, char *c,int limit)
{
	int ret = 0;
	char cmd[WRITE_BUFFER_SIZE] = "channel?\r";
	char temp[MAXLEN] = {0};
	ret = get(hdl, cmd, temp);
	sscanf_s(temp,"channel?\r%[0-9]", c, MAXLEN);
	return ret;
}

int fnMCLS1_DLL_GetTargetTemperature(int hdl, char *c,int limit)
{
	int ret = 0;
	char cmd[WRITE_BUFFER_SIZE] = "target?\r";
	char temp[MAXLEN] = {0};
	ret = get(hdl, cmd, temp);
	sscanf_s(temp, "target?\r%[0-9'.']", c, MAXLEN);
	return ret;
}

int fnMCLS1_DLL_GetActualTemperature(int hdl, char *c,int limit)
{
	int ret = 0;
	char cmd[WRITE_BUFFER_SIZE] = "temp?\r";
	char temp[MAXLEN] = {0};
	ret = get(hdl, cmd, temp);
	sscanf_s(temp,"temp?\r%[0-9'.']", c, MAXLEN);
	return ret;
}

int fnMCLS1_DLL_GetActualCurrent(int hdl, char *c,int limit)
{
	int ret = 0;
	char cmd[WRITE_BUFFER_SIZE] = "current?\r";
	char temp[MAXLEN] = {0};
	ret = get(hdl, cmd, temp);
	sscanf_s(temp,"current?\r%[0-9'.']", c, MAXLEN);
	return ret;
}

int fnMCLS1_DLL_GetActualPower(int hdl, char *c,int limit)
{
	int ret = 0;
	char cmd[WRITE_BUFFER_SIZE] = "power?\r";
	char temp[MAXLEN] = {0};
	ret = get(hdl, cmd, temp);
	sscanf_s(temp,"power?\r%[0-9'.']", c, MAXLEN);
	return ret;
}

int fnMCLS1_DLL_GetSystemEnable(int hdl, char *c,int limit)
{
	int ret = 0;
	char cmd[WRITE_BUFFER_SIZE] = "system?\r";
	char temp[MAXLEN] = {0};
	ret = get(hdl, cmd, temp);
	sscanf_s(temp,"system?\r%[0-9]", c, MAXLEN);
	return ret;
}

int fnMCLS1_DLL_GetEnable(int hdl, char *c,int limit)
{
	int ret = 0;
	char cmd[WRITE_BUFFER_SIZE] = "enable?\r";
	char temp[MAXLEN] = {0};
	ret = get(hdl, cmd, temp);
	sscanf_s(temp,"enable?\r%[0-9]", c, MAXLEN);
	return ret;
}

int fnMCLS1_DLL_GetStatus(int hdl, char *c,int limit)
{
	int ret = 0;
	char cmd[WRITE_BUFFER_SIZE] = "statword?\r";
	char temp[MAXLEN] = {0};
	ret = get(hdl, cmd, temp);
	sscanf_s(temp,"statword?\r%[0-9]",c, MAXLEN);
	return ret;
}

int fnMCLS1_DLL_GetID(int hdl, char *c,int limit)
{
	int ret = 0;
	char cmd[WRITE_BUFFER_SIZE] = "id?\r";
	char temp[MAXLEN] = {0};
	ret = get(hdl, cmd, temp);
	sscanf_s(temp,"id?\r%[0-9a-zA-Z .]", c, MAXLEN);
	return ret;
}
