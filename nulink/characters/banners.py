"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import nulink


NLK_BANNER = r'''
        
███╗   ██╗██╗     ██╗  ██╗
████╗  ██║██║     ██║ ██╔╝
██╔██╗ ██║██║     █████╔╝ 
██║╚██╗██║██║     ██╔═██╗ 
██║ ╚████║███████╗██║  ██╗
╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝
'''


NULINK_BANNER = r"""

 __   __     __  __     __         __     __   __     __  __    
/\ "-.\ \   /\ \/\ \   /\ \       /\ \   /\ "-.\ \   /\ \/ /    
\ \ \-.  \  \ \ \_\ \  \ \ \____  \ \ \  \ \ \-.  \  \ \  _"-.  
 \ \_\\"\_\  \ \_____\  \ \_____\  \ \_\  \ \_\\"\_\  \ \_\ \_\ 
  \/_/ \/_/   \/_____/   \/_____/   \/_/   \/_/ \/_/   \/_/\/_/ 


version {}
""".format(nulink.__version__)


ALICE_BANNER = r"""

    / \  | (_) ___ ___
   / _ \ | | |/ __/ _ \
  / ___ \| | | (_|  __/
 /_/   \_|_|_|\___\___|

 the Authority.
"""


BOB_BANNER = r"""

oooooooooo              oooo       
 888    888   ooooooo    888ooooo  
 888oooo88  888     888  888    888
 888    888 888     888  888    888
o888ooo888    88ooo88   o888ooo88  

the BUIDLer.
"""


ENRICO_BANNER = r"""
 ___                
 )_  _   _ o  _  _  
(__ ) ) )  ( (_ (_) 

the Encryptor.
{}
"""


URSULA_BANNER = r'''


 ,ggg,         gg                                                     
dP""Y8a        88                                   ,dPYb,            
Yb, `88        88                                   IP'`Yb            
 `"  88        88                                   I8  8I            
     88        88                                   I8  8'            
     88        88   ,gggggg,    ,g,     gg      gg  I8 dP    ,gggg,gg 
     88        88   dP""""8I   ,8'8,    I8      8I  I8dP    dP"  "Y8I 
     88        88  ,8'    8I  ,8'  Yb   I8,    ,8I  I8P    i8'    ,8I 
     Y8b,____,d88,,dP     Y8,,8'_   8) ,d8b,  ,d8b,,d8b,_ ,d8,   ,d8b,
      "Y888888P"Y88P      `Y8P' "YY8P8P8P'"Y88P"`Y88P'"Y88P"Y8888P"`Y8


the Untrusted Re-Encryption Proxy.
{}
'''


STAKEHOLDER_BANNER = r"""
 ____    __            __                      
/\  _`\ /\ \__        /\ \                     
\ \,\L\_\ \ ,_\    __ \ \ \/'\      __   _ __  
 \/_\__ \\ \ \/  /'__`\\ \ , <    /'__`\/\`'__\
   /\ \L\ \ \ \_/\ \L\.\\ \ \\`\ /\  __/\ \ \/ 
   \ `\____\ \__\ \__/.\_\ \_\ \_\ \____\\ \_\ 
    \/_____/\/__/\/__/\/_/\/_/\/_/\/____/ \/_/ 
   
The Holder of Stakes.                                      
"""
