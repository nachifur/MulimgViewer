"""Mutable playback and cache state shared by image/video controllers."""


class SharedConfig:
    def __init__(self):
        '''Variables shared by MulimgViewer and VideoManager.'''
        self.cache_num = 2 #Number of caches
        self.cache_multiplier = 1 # Outer video cache radius / priority radius
        self.skip_frames = 0 #Number of frames to skip
        self.power_mode = 2 # 1 Eco, 2 Balanced, 3 Performance, 4 Maximum
        self.memory_budget = None # Soft budget for concurrent pixel working sets
        self.thread = 4 # Internal processing budget; populated from power_mode
        self.thread_allocation = None # Actual extract/stitch pool sizes
        self.thread_allocation_recommend = None
        self.video_mode = False #Video mode
        self.interval = 1.0 #Playback interval
        self.manual_interval = None # Last user-entered video interval; auto writes never change it
        self.is_playing = False #Whether currently playing
        self.play_direction = 1 #Playback direction
        self.real_video_path = [] #Actual video paths, ending in mp4
        self.video_path = [] #Video Cache Path
        self.parallel_to_sequential = False #Parallel to sequential
        self.parallel_sequential = False #Parallel to sequential
        self.input_mode = 0 # Input mode
        self.video_fps_list = [] #Video fps
        self.batch_idx = 0 #Current batch index
        self.count_per_action = 1 #Frames processed per action
        self.video_num_list = [] #Maximum frames for each video
        self.current_video_index = 0 #Current video index
        self.last_direction = 0 #Last playback direction
        self.cache_img = [] #Position to store stitched images
        self.image_cache_img = [] #Image mode stitch cache False
        self.image_cache_paths = [] #Image mode cache path list
        self.image_disk_cache_dir = "cache_frames/stitch_cache"
        self.debug_video = False #Video mode debug output
        self.debug_image = False #Image mode debug output
        self.debug_thread = False #Thread debug output
        #self.debug_thread = True
        #self.debug_video = True
        self.interval_recommend = None #Playback interval recommendation
        self.video_last_message = "" # Most recent video error/diagnostic information

