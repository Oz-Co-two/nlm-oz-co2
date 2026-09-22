/**
 * Shared layout / chart constants (mirrors runtime defaults).
 * Runtime closure still owns live mutable copies where needed.
 */
export const VERSION = 'nlm-modular-1';

/** Grid / timeline spacing (editor 3D + NLE). */
export const LANE = 0.62;
export const LAYER = 0.62;
export const BASE_Y = 0.7;
export const ZPB = 2.52; // Z per beat

/** Default note / laser colors. */
export const DEFAULT_NOTE_RED = 0xff274d;
export const DEFAULT_NOTE_BLUE = 0x3092ff;
export const DEFAULT_LASER_RED = 0xff274d;
export const DEFAULT_LASER_BLUE = 0x3092ff;

/** Cut direction icons / vectors (Beat Saber). */
export const DIRICON = {0:'↑',1:'↓',2:'←',3:'→',4:'↖',5:'↗',6:'↙',7:'↘',8:'•'};
export const DIRV = {0:[0,1],1:[0,-1],2:[-1,0],3:[1,0],4:[-1,1],5:[1,1],6:[-1,-1],7:[1,-1],8:[0,0]};
export const ROT = [1,6,2,4,0,5,3,7,8];
export const DIR_ANGLE = {0:0,5:45,3:90,7:135,1:180,6:225,2:270,4:315};

export const FONT = '"M PLUS Rounded 1c",sans-serif';

/** Difficulty keys used in projDiffs / export. */
export const DIFF_KEYS = ['Easy', 'Normal', 'Hard', 'Expert', 'ExpertPlus'];
