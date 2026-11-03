"""Systematic Hamming(15,11), even parity, column-wise block interleaving.

Positions 1,2,4,8 are parity; data fill remaining positions in MSB order.
Zero-pad information to 11 bits, then pad the interleaved stream to dibits.
Each block's original byte length is supplied by the public packet format.
"""
import numpy as np

DATA=np.array([2,4,5,6,8,9,10,11,12,13,14])
POSITIONS=np.arange(1,16)

def symbol_count(byte_count):
    return (((byte_count*8+10)//11)*15+1)//2

def encode(data):
    bits=np.unpackbits(np.frombuffer(data,dtype=np.uint8))
    blocks=(len(bits)+10)//11
    info=np.pad(bits,(0,blocks*11-len(bits))).reshape(blocks,11)
    words=np.zeros((blocks,15),dtype=np.uint8);words[:,DATA]=info
    for parity in (1,2,4,8):
        words[:,parity-1]=np.bitwise_xor.reduce(words[:,(POSITIONS & parity)!=0],axis=1)
    stream=words.T.ravel()
    stream=np.pad(stream,(0,len(stream)%2))
    return stream.reshape(-1,2) @ np.array([2,1])

def decode(values,byte_count):
    values=np.asarray(values,dtype=np.uint8)
    if len(values)!=symbol_count(byte_count):raise ValueError('纠错块长度不一致')
    bits=np.column_stack((values>>1,values&1)).ravel()
    blocks=(byte_count*8+10)//11
    words=bits[:blocks*15].reshape(15,blocks).T.copy()
    raw=np.packbits(words[:,DATA].ravel()[:byte_count*8]).tobytes()
    syndrome=np.zeros(blocks,dtype=np.uint8)
    for parity in (1,2,4,8):
        syndrome|=np.bitwise_xor.reduce(words[:,(POSITIONS & parity)!=0],axis=1)*parity
    affected=np.flatnonzero(syndrome)
    words[affected,syndrome[affected]-1]^=1
    corrected=np.packbits(words[:,DATA].ravel()[:byte_count*8]).tobytes()
    return corrected,raw,int(len(affected)),blocks
