// The following ifdef block is the standard way of creating macros which make exporting 
// from a DLL simpler. All files within this DLL are compiled with the UART_LIBRARY_EXPORTS
// symbol defined on the command line. This symbol should not be defined on any project
// that uses this DLL. This way any other project whose source files include this file see 
// UART_LIBRARY_API functions as being imported from a DLL, whereas this DLL sees symbols
// defined with this macro as being exported.
#ifdef UART_LIBRARY_EXPORTS
#define UART_LIBRARY_API extern "C" __declspec(dllexport)
#else
#define UART_LIBRARY_API extern "C" __declspec(dllimport)
#endif

/// <summary>
///  open port function.
/// </summary>
/// <param name="port">com port string of the device to be opened, use fnUART_LIBRARY_list function to get exist list first.</param>
/// <param name="nBaud">bit per second of port</param>
/// <param name="time">set timeout value in (s)</param>
/// <returns> non-negtive number: hdl number returned successfully; negtive number : failed.</returns>
UART_LIBRARY_API int fnUART_LIBRARY_open(char *port, int nBaud, int timeout);

/// <summary>
/// check opened status of port
/// </summary>
/// <param name="port">Com port string of the device to be checked.</param>
/// <returns> 0: port is not opened; 1 : port is opened.</returns>
UART_LIBRARY_API int fnUART_LIBRARY_isOpen(char *port);

/// <summary>
/// list all the possible port on this computer.
/// </summary>
/// <param name="nPort">port list returned string include com port string and device descriptor, separated by comma</param>
/// <param name="var">max length value of nPort buffer</param>
/// <returns>non-negtive number: number of device in the list; negtive number : failed.</returns>
UART_LIBRARY_API int fnUART_LIBRARY_list(char *port, int var);

/// <summary>
/// close current opend port
/// </summary>
/// <param name="hdl">handle of port.</param>
/// <returns> 0: success; negtive number : failed.</returns>
UART_LIBRARY_API int fnUART_LIBRARY_close(int hdl);

/// <summary>
/// <p>write string to device through opened port.</p>
/// <p>make sure the port was opened successful before call this function.</p>
/// </summary>
/// <param name="hdl">handle of port.</param>
/// <param name="b">input string</param>
/// <param name="size">size of string to be written.</param>
/// <returns>non-negtive number: number of bytes written; negtive number : failed.</returns>
UART_LIBRARY_API int fnUART_LIBRARY_write(int hdl, char *b, int size);

/// <summary>
/// <p>read string from device through opened port.</p>
/// <p>make sure the port was opened successful before call this function.</p>
/// </summary>
/// <param name="hdl">handle of port.</param>
/// <param name="b">returned string buffer</param>
/// <param name="limit">
/// <p>ABS(limit): max length value of b buffer. </p>
/// <p>SIGN(limit) == 1 : wait RX event until time out value expired;</p>
/// <p>SIGN(limit) == -1: INFINITE wait event untill RX has data;</p>
/// </param>
/// <returns>non-negtive number: size of actual read data in byte; negtive number : failed.</returns>
UART_LIBRARY_API int fnUART_LIBRARY_read(int hdl, char *b, int limit);

/// <summary>
/// <p>set command to device according to protocal in manual.</p>
/// <p>make sure the port was opened successful before call this function.</p>
/// <p>make sure this is the correct device by checking the ID string before call this function.</p>
/// </summary>
/// <param name="hdl">handle of port.</param>
/// <param name="c">input command string</param>
/// <param name="var">lenth of input command string (<255)</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
UART_LIBRARY_API int fnUART_LIBRARY_Set(int hdl, char *c,int var);

/// <summary>
/// <p>set command to device according to protocal in manual and get the return string.</p>
/// <p>make sure the port was opened successful before call this function.</p>
/// <p>make sure this is the correct device by checking the ID string before call this function.</p>
/// </summary>
/// <param name="hdl">handle of port.</param>
/// <param name="c">input command string (<255)</param>
/// <param name="d">output string (<255)</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
UART_LIBRARY_API int fnUART_LIBRARY_Get(int hdl, char *c,char *d);

/// <summary>
/// this function is not supported yet.
/// </summary>
UART_LIBRARY_API int fnUART_LIBRARY_Req(int hdl, char *c,char *d);

/// <summary>
/// set time out value for read or write process.
/// </summary>
/// <param name="hdl">handle of port.</param>
/// <param name="time">time out value</param>
UART_LIBRARY_API void fnUART_LIBRARY_timeout(int hdl, int time);

/// <summary>
/// Purge the RX and TX buffer on port.
/// </summary>
/// <param name="hdl">handle of port.</param>
/// <param name="flag">
/// <p>FT_PURGE_RX: 0x01</p>
/// <p>FT_PURGE_TX: 0x02</p>
///</param>
/// <returns> 0: success; negtive number : failed.</returns>
UART_LIBRARY_API int fnUART_LIBRARY_Purge(int hdl, int flag);
