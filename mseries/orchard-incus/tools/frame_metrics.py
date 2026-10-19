"""Presentation-feedback summaries; absent feedback is never zero latency."""
import statistics


def percentile(values, fraction):
    values = sorted(values)
    return round(values[int((len(values) - 1) * fraction)], 3) if values else None


def distribution(values):
    return {'p50': percentile(values, .5), 'p95': percentile(values, .95),
            'max': round(max(values), 3) if values else None}


def summarize_frames(raw, actions, minimum_actions=16):
    presented = sorted((row for row in raw if row['complete'] and row['presentation_us'] > 0),
                       key=lambda row: row['counter'])
    latency = [(row['presentation_us'] - row['start_us']) / 1000
               for row in presented if row['presentation_us'] >= row['start_us']]
    stamps = sorted({row['presentation_us'] for row in presented})
    gaps = [(b - a) / 1000 for a, b in zip(stamps, stamps[1:])]
    matched = []
    for timestamp, counter in actions:
        frame = next((row for row in presented if row['counter'] >= counter
                      and row['presentation_us'] >= timestamp), None)
        if frame:
            matched.append((frame['presentation_us'] - timestamp) / 1000)
    refresh = [row['refresh_us'] for row in presented if row['refresh_us'] > 0]
    status = ('unavailable' if not presented else
              'complete' if len(actions) >= minimum_actions and len(matched) == len(actions)
              else 'incomplete')
    return {'status': status, 'measured': len(raw), 'presentation_feedback': len(presented),
            'requested_actions': len(actions), 'minimum_actions': minimum_actions,
            'refresh_interval_us': statistics.median(refresh) if refresh else None,
            'frame_start_to_presentation_ms': distribution(latency),
            'presentation_gap_ms': distribution(gaps),
            'programmatic_action_to_presentation_ms': {'samples': len(matched), **distribution(matched)},
            'limits': 'Programmatic GTK navigation, not physical input-to-photon. Missing or sparse feedback does not establish latency stability. Long gaps are retained, not discarded as outliers.'}
