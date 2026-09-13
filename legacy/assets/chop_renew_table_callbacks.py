def run_renew_table():
    try:
        op('renew_table').run()
    except Exception as e:
        try:
            debug('[chop_renew_table_callbacks] renew_table run failed', e)
        except Exception:
            pass


def onValueChange(channel, sampleIndex, val, prev):
    run_renew_table()
    return


def onOffToOn(channel, sampleIndex, val, prev):
    run_renew_table()
    return
