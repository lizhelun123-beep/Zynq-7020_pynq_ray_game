"""Offline C replay of recorded UART events. Never opens a serial port or board."""
import argparse
from collections import Counter
import hashlib
from itertools import groupby
import json
from pathlib import Path
import sys
from types import SimpleNamespace


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--trace',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='New directory, preserved if already present')
    args=parser.parse_args()
    project=args.project.resolve()
    output=args.output.resolve()
    if output.exists():parser.error('Refuse existing output: '+str(output))
    sys.path.insert(0,str(project))
    from pc_vision.board_wire import BinaryParser
    from pc_vision.board_pose import PoseFrame,ClockBounds,PoseOrder
    from pc_vision.board_control import ControlFrame,ControlTransportEvent
    from pc_vision.board_native import NativeBoardGame
    from pc_vision.godot_bridge import BoardGamePresenter

    data=args.trace.read_bytes()
    rows=[json.loads(line) for line in data.decode('utf-8').splitlines() if line.strip()]
    if not rows:parser.error('Empty trace')
    if any(a['time_ms']>b['time_ms'] for a,b in zip(rows,rows[1:])):
        parser.error('Trace order is not monotonic')
    config=json.loads((project/'pc_vision/game_config.json').read_text(encoding='utf-8'))
    output.mkdir(parents=True)
    wire=BinaryParser();order=PoseOrder();poses=[];snapshots=[];accepted=[]
    core=NativeBoardGame()
    transport=SimpleNamespace(port=rows[0].get('port',''),queue_level=lambda *a:None,
                              queue_start=lambda *a:None,queue_reset=lambda *a:None)
    presenter=BoardGamePresenter(core,config,transport)
    clock=None;connected=False;epoch=0;sync_sent={};first_result=None
    try:
        for now,group in groupby(rows,key=lambda r:r['time_ms']):
            frame=None;controls=[];events=[]
            for row in group:
                event=row['event']
                if event=='CONNECTED':connected=True;epoch=row['epoch']
                elif event=='DISCONNECTED':connected=False
                elif event=='QUEUED':
                    # Infer UI requests from actual queued transport commands.
                    # These are replay inputs, not a recording of live C output.
                    if row['command']=='LEVEL2':
                        presenter.level_nonce=row['nonce']
                        presenter.action(dict(action='select',level_id=row['level_id']),now,connected)
                    elif row['command']=='START2':presenter.action(dict(action='start'),now,connected)
                    elif row['command']=='RESET2':presenter.action(dict(action='menu'),now,connected)
                elif event=='TX_SENT':
                    if row['command']=='SYNC2':sync_sent[row['nonce']]=row['sent_ms']
                    else:events.append(ControlTransportEvent('SENT',epoch,row['command'],row['generation'],
                        row['nonce'],row.get('level_id',0),row['attempt'],row['sent_ms'],row['started_ms']))
                elif event=='RX_BYTES':
                    for message in wire.feed(bytes.fromhex(row['data_hex'])):
                        if isinstance(message,PoseFrame):
                            ok,_=order.accept(message)
                            poses.append(dict(received_ms=now,order_accepted=ok,**message.record()))
                            if ok:frame=message
                elif event=='SYNC_RX' and row.get('clock_accepted'):
                    sent=sync_sent[row['nonce']]
                    board_sent=row.get('board_sent_ms',row['board_ms'])
                    received=sent+row['round_trip_ms']+(board_sent-row['board_ms'])
                    clock=ClockBounds(sent,received,row['board_ms'],board_sent)
                elif event=='CONTROL_RX' and row.get('matched'):
                    controls.append(ControlFrame(row['command'],row.get('level_id',0),row['generation'],
                        *row.get('emitter',[0,0,0,0]),row['nonce'],row.get('board_ms',0),row.get('error_code',0)))
            snapshot=presenter.update(frame,epoch,connected,clock,now,controls=controls,transport_events=events)
            if frame is not None or controls:snapshots.append(dict(replay_pc_ms=now,**snapshot))
            if frame is not None and snapshot.get('board_frame'):
                if snapshot['board_frame']['sequence']==frame.sequence and snapshot.get('valid'):
                    accepted.append(frame.sequence)
            if first_result is None and snapshot['screen']=='result':first_result=dict(replay_pc_ms=now,**snapshot)
    finally:
        core.close()
    for name,records in [('decoded_poses.jsonl',poses),('offline_c_replay.jsonl',snapshots)]:
        with (output/name).open('x',encoding='utf-8') as stream:
            for record in records:stream.write(json.dumps(record,ensure_ascii=False)+'\n')
    result=dict(environment='OFFLINE_C_REPLAY_FROM_ACTUAL_UART',hardware_operations=0,
        trace_sha256=hashlib.sha256(data).hexdigest(),native_core_sha256=hashlib.sha256(core.path.read_bytes()).hexdigest(),
        recorded_pc_build=rows[0].get('build'),events=dict(Counter(r['event'] for r in rows)),
        pose_frames=len(poses),valid_board_poses=sum(p['valid'] for p in poses),
        pose_status=dict(Counter(p['status'] for p in poses)),parser_rejections=wire.rejected,
        accepted_sequences=accepted,first_result=first_result,
        scope='QUEUED mapped to select/start/menu; updates at event times; receive instant from recorded RTT. No live C snapshots or UI recording are manufactured.')
    (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(environment=result['environment'],pose_frames=len(poses),valid=result['valid_board_poses'],
        parser_rejections=wire.rejected,result=None if first_result is None else first_result.get('result')),ensure_ascii=False))


if __name__=='__main__':main()
