/* Select separate physical cores before SMT siblings. MIT. */
#ifndef SR3_CPU_AFFINITY_H
#define SR3_CPU_AFFINITY_H
#include <windows.h>
typedef struct Sr3CpuCore { DWORD_PTR mask; unsigned efficiency; } Sr3CpuCore;
unsigned sr3_cpu_topology(Sr3CpuCore *cores,unsigned capacity);
DWORD_PTR sr3_cpu_select(const Sr3CpuCore *cores,unsigned count,DWORD_PTR available,unsigned limit);
unsigned sr3_cpu_physical_count(const Sr3CpuCore *cores,unsigned count,DWORD_PTR mask);
#endif
