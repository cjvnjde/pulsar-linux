import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import java.io.*;
public class ExportDecompiled extends GhidraScript {
 public void run() throws Exception {
  File dir=new File(getScriptArgs()[0]); dir.mkdirs();
  DecompInterface d=new DecompInterface(); d.openProgram(currentProgram);
  for(Function f:currentProgram.getFunctionManager().getFunctions(true)) {
   if(f.isExternal()||f.isThunk()) continue;
   DecompileResults r=d.decompileFunction(f,30,monitor);
   if(r.decompileCompleted()) {
    try(PrintWriter p=new PrintWriter(new File(dir,f.getEntryPoint()+".c"))) {p.println(r.getDecompiledFunction().getC());}
   }
  }
  d.dispose();
 }
}
