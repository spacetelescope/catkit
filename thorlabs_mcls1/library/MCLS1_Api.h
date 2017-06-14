
/// <summary>
/// load uart_library_win32_mcls.dll
/// </summary>
/// <returns>non-negtive number: succeed; negtive number : failed.</returns>
int init_MCLS1();

/// <summary>
/// list all the possible Serial port on this computer.
/// </summary>
/// <param name="port">port list returned string, seperated by comma</param>
/// <param name="var">max length value of nPort buffer</param>
/// <returns>non-negtive number: number of device in the list; negtive number : failed.</returns>
int fnMCLS1_DLL_List(char* port, int var);

/// <summary>
///  open the COM port function.
/// </summary>
/// <param name="port">COM port string to be open, check the correct value through device manager.</param>
/// <returns> non-negtive number: hdl number returned successfully; negtive number : failed.</returns>
int fnMCLS1_DLL_Open(char* port);

/// <summary>
/// closed current opend port
 // <param name="hdl">handle of port, return value of fnMCLS1_DLL_Open.</param>
/// </summary>
int fnMCLS1_DLL_Close(int hdl);

/// <summary>
/// <p>set active channel of MCLS device.</p>
/// <p>input range:1-4.</p>
/// </summary>
/// <param name="v">active channel number</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
int fnMCLS1_DLL_SetActiveChannel(int hdl, int v);

/// <summary>
/// <p>set target temperature of active channel.</p>
/// <p>input range:20-30 Celsius degree.</p>
/// </summary>
/// <param name="v">input target temperature</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
int fnMCLS1_DLL_SetTargeTemperature(int hdl, float v);

/// <summary>
/// <p>set current of active channel.</p>
/// <p> input range: differs from different laser used, please reference laser spec</p>
/// </summary>
/// <param name="v">input current</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
int fnMCLS1_DLL_SetCurrent(int hdl, float v);

/// <summary>
/// <p>set enable/disable for active channel.</p>
/// </summary>
/// <param name="v">input 1: enable, 0: disable</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
int fnMCLS1_DLL_SetEnable(int hdl, int v);

/// <summary>
/// <p>set enable/disable of MCLS device.</p>
/// </summary>
/// <param name="v">input 1: enable, 0: disable </param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
int fnMCLS1_DLL_SetSystemEnable(int hdl, int v);

/// <summary>
/// <p>get the active channel number from MCLS device.</p>
/// </summary>
/// <param name="c">returned string buffer</param>
/// <param name="limit">max lenth value of c buffer</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
int fnMCLS1_DLL_GetActiveChannel(int hdl, char *c, int limit);

/// <summary>
/// <p>get the value of target temperature of active channel from MCLS device.</p>
/// </summary>
/// <param name="hdl">handle of port.</param>
/// <param name="c">returned string buffer</param>
/// <param name="limit">max lenth value of c buffer</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
int fnMCLS1_DLL_GetTargetTemperature(int hdl, char *c, int limit);

/// <summary>
/// <p>get the value of actual temperature of active channel from MCLS device.</p>
/// </summary>
/// <param name="c">returned string buffer</param>
/// <param name="limit">max lenth value of c buffer</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
int fnMCLS1_DLL_GetActualTemperature(int hdl, char *c, int limit);

/// <summary>
/// <p>get Actual Current of active channel from MCLS device.</p>
/// </summary>
/// <param name="hdl">handle of port.</param>
/// <param name="c">returned string buffer</param>
/// <param name="limit">max lenth value of c buffer</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
int fnMCLS1_DLL_GetActualCurrent(int hdl, char *c, int limit);

/// <summary>
/// <p>get Actual power of active channel from MCLS device.</p>
/// </summary>
/// <param name="c">returned string buffer</param>
/// <param name="limit">max lenth value of c buffer</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
int fnMCLS1_DLL_GetActualPower(int hdl, char *c, int limit);

/// <summary>
/// <p>get the status of system enable for MCLS device.</p>
/// </summary>
/// <param name="c">returned string buffer</param>
/// <param name="limit">max lenth value of c buffer</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
int fnMCLS1_DLL_GetSystemEnable(int hdl, char *c, int limit);

/// <summary>
/// <p>get the status of active channel enable for MCLS device.</p>
/// </summary>
/// <param name="c">returned string buffer</param>
/// <param name="limit">max lenth value of c buffer</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
int fnMCLS1_DLL_GetEnable(int hdl, char *c, int limit);

/// <summary>
/// <p>get the status of active channel.</p>
/// </summary>
/// <param name="c">returned string buffer</param>
/// <param name="limit">max lenth value of c buffer</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
int fnMCLS1_DLL_GetStatus(int hdl, char *c, int limit);

/// <summary>
/// <p>get ID of MCLS device.</p>
/// </summary>
/// <param name="c">returned string buffer</param>
/// <param name="limit">max lenth value of c buffer</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
int fnMCLS1_DLL_GetID(int hdl, char *c, int limit);

