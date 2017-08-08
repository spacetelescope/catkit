using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Thorlabs.TSP;

namespace thorlabs_sensor_cs
{
    class Program
    {
        static void Main(string[] args)
        {
            TLTSP tsp = new TLTSP("USB0::0x1313::0x80F8::M00306091::INSTR", true, true);

            // Internal temp is internal to the usb sensor.  External is what we need.
            Double internal_temp;
            tsp.measTemperature(1, out internal_temp);

            Double humidity;
            tsp.fetchHumidity(out humidity);

            Double external_temp;
            tsp.getTemperatureData(2, 0, out external_temp);
            string str = "temp=" + external_temp.ToString("0.##") + " humidity=" + humidity.ToString("0.##");
            Console.WriteLine(str);
        }
    }
}
