from collections import defaultdict, OrderedDict

import numpy as np
import pylab as plt

from utils.utils import dist
from utils.kalman import RTSSmoother, _plot_rts_smoother

CUM_DIST_CUTOFF = 100


class Match(object):
    '''Represents one match between a best track and a vorticity track'''
    def __init__(self, best_track, vort_track):
        self.best_track = best_track
        self.vort_track = vort_track
        self.cum_dist = 0
        self.overlap = 1
        self.is_too_far_away = False
        self.overlap_start = max(best_track.dates[0], vort_track.dates[0])
        self.overlap_end = min(best_track.dates[-1], vort_track.dates[-1])

    def av_dist(self):
        '''Returns the average distance between the best and vorticity tracks'''
        return self.cum_dist / self.overlap


def match(vort_tracks_by_date, best_tracks):
    '''Takes all vorticity tracks and best tracks and matches them up

    Uses CUM_DIST_CUTOFF to decide whether the two tracks are too far apart

    :param vort_tracks_by_date: dict with dates as keys and lists of vort tracks as values
    :param best_tracks: list of best tracks
    :returns: OrderedDict of Match objects
        * key: (best_track, vortmax) tuple
        * value: Match object
    '''
    matches = OrderedDict()

    for best_track in best_tracks:
        for lon, lat, date in zip(best_track.lons, best_track.lats, best_track.dates):
            if date in vort_tracks_by_date.keys():
                vort_tracks = vort_tracks_by_date[date]
                for vortmax in vort_tracks:
                    if (best_track, vortmax) in matches:
                        match = matches[(best_track, vortmax)]
                        match.overlap += 1
                    else:
                        match = Match(best_track, vortmax)
                        matches[(best_track, vortmax)] = match
                        if match.is_too_far_away:
                            continue

                    match.cum_dist += dist(vortmax.vortmax_by_date[date].pos, (lon, lat))
                    if match.cum_dist > CUM_DIST_CUTOFF:
                        match.is_too_far_away = True

    return matches


def combined_match(best_tracks, all_matches):
    '''Uses all best tracks and matches to combine all matches for each best track

    :param best_tracks: list of best tracks
    :param all_matches: all matches to search through
    :returns: dict of combined_matches (key: best track, value: list of matches)
    '''

    combined_matches = {}

    for best_track in best_tracks:
        combined_matches[best_track] = []

    for matches in all_matches:
        for match in matches:
            combined_matches[match.best_track].append(match)

    return combined_matches


def _cum_dist(best_track, vortmax_by_date):
    '''Calculated the cumalitive distance between a best and vortmax track'''
    d = 0
    overlap = 0
    for lon, lat, date in zip(best_track.lons, best_track.lats, best_track.dates):
        try:
            d += dist(vortmax_by_date[date].pos, (lon, lat)) ** 2
            overlap += 1
        except:
            pass
    return d, overlap


def _optimise_rts_smoothing(combined_matches):
    '''Experimental function looking at optimizing RTS smoothing'''
    F = np.matrix([[1., 0., 1., 0.],
                   [0., 1., 0., 1.],
                   [0., 0., 1., 0.],
                   [0., 0., 0., 1.]])
    H = np.matrix([[1., 0., 0., 0.],
                   [0., 1., 0., 0.]])
    Q = np.matrix([[2., 1., 1., 1.],
                   [1., 2., 1., 1.],
                   [1., 1., 2., 1.],
                   [1., 1., 1., 2.]])
    R = np.matrix([[2., 1.],
                   [1., 2.]])

    c = 1

    fig = None
    for best_track, vort_tracks in combined_matches.items():
        for vort_track in vort_tracks:
            if fig:
                fig.canvas.manager.window.attributes('-topmost', 0)
            fig = plt.figure(c)
            fig.canvas.manager.window.attributes('-topmost', 1)
            _optimize(best_track, vort_track)
            c += 1


def _optimize(best_track, vort_track):
    '''Experimental function looking at optimizing RTS'''
    class __Tmp(object):
        pass

    F = np.matrix([[1., 0., 1., 0.],
                   [0., 1., 0., 1.],
                   [0., 0., 1., 0.],
                   [0., 0., 0., 1.]])
    H = np.matrix([[1., 0., 0., 0.],
                   [0., 1., 0., 0.]])
    Q = np.matrix([[2., 1., 1., 1.],
                   [1., 2., 1., 1.],
                   [1., 1., 2., 1.],
                   [1., 1., 1., 2.]])
    R = np.matrix([[2., 1.],
                   [1., 2.]])

    baseline_dist, overlap = _cum_dist(best_track, vort_track.vortmax_by_date)

    pos = np.array([vm.pos for vm in vort_track.vortmaxes])
    rts_smoother = RTSSmoother(F, H)
    smoothed_dict = OrderedDict()
    filtered_dict = OrderedDict()

    min_d = baseline_dist
    print('baseline {0}'.format(baseline_dist))
    optimum_param = None

    x = np.matrix([pos[0, 0], pos[0, 1], 0, 0]).T
    P = np.matrix(np.eye(4)) * 10

    plt.clf()
    plt.title(str(baseline_dist))
    plt.plot(pos[:, 0], pos[:, 1], 'k+')
    plt.plot(best_track.lons, best_track.lats, 'b-')
    plt.pause(0.01)

    for q_param in np.arange(1e-4, 1e-2, 5e-4):
        for r_param in np.arange(1e-2, 1e0, 5e-2):
            xs, Ps = rts_smoother.process_data(pos, x, P, Q * q_param, R * r_param)
            smoothed_pos = np.array(xs)[:, :2, 0]
            # import ipdb; ipdb.set_trace()
            filtered_pos = np.array(rts_smoother.filtered_xs)[:, :2, 0]
            for i, date in enumerate(vort_track.vortmax_by_date.keys()):
                tmp = __Tmp()
                tmp.pos = smoothed_pos[i]
                smoothed_dict[date] = tmp
                tmp = __Tmp()
                tmp.pos = filtered_pos[i]
                filtered_dict[date] = tmp

            smoothed_new_d, overlap = _cum_dist(best_track, smoothed_dict)
            filtered_new_d, overlap = _cum_dist(best_track, filtered_dict)

            if overlap >= 6 and smoothed_new_d < min_d:
                optimum_param = (q_param, r_param, 'smoothed')
                print('new optimum param: {0}'.format(optimum_param))
                min_d = smoothed_new_d
                print('min dist {0}'.format(min_d))

                _plot_rts_smoother(rts_smoother)
                plt.title(str(optimum_param))
                plt.plot(best_track.lons, best_track.lats, 'b-')
                plt.pause(0.01)
            if overlap >= 6 and filtered_new_d < min_d:
                optimum_param = (q_param, r_param, 'filtered')
                print('new optimum param: {0}'.format(optimum_param))
                min_d = filtered_new_d

                _plot_rts_smoother(rts_smoother)
                plt.title(str(optimum_param))
                plt.plot(best_track.lons, best_track.lats, 'b-')
                plt.pause(0.01)

    print(min_d / baseline_dist)
