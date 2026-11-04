#!/usr/bin/env python3
"""One explicit recovery attempt; never logs credential values or server bodies."""
from collect import authenticated_stock

if __name__=='__main__':
    try:
        authenticated_stock()
        print('KRX authentication verified; scheduled collectors may resume.')
    except Exception as exc:
        safe=str(exc) if str(exc).startswith('KRX ') else type(exc).__name__
        print('KRX authentication check failed: '+safe)
        raise SystemExit(1)
