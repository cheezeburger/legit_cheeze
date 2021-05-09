import keystate_manager as km
import player_controller as pc
import screen_processor as sp
import terrain_analyzer as ta
import directinput_constants as dc
import rune_solver as rs
import logging, math, time, random
import random


class CustomLogger:
    def __init__(self, logger_obj, logger_queue):
        self.logger_obj = logger_obj
        self.logger_queue = logger_queue

    def debug(self, *args):
        self.logger_obj.debug(" ".join([str(x) for x in args]))
        if self.logger_queue:
            self.logger_queue.put(("log", " ".join([str(x) for x in args])))

    def exception(self, *args):
        self.logger_obj.exception(" ".join([str(x) for x in args]))
        if self.logger_queue:
            self.logger_queue.put(("log", " ".join([str(x) for x in args])))


class MacroController:
    # 3rd param rune_model_dir=r"arrow_classifier_keras_gray.h5",
    def __init__(self, keymap=km.DEFAULT_KEY_MAP, log_queue=None):

        # sys.excepthook = self.exception_hook

        self.screen_capturer = sp.MapleScreenCapturer()
        logger = logging.getLogger(self.__class__.__name__)
        logger.setLevel(logging.DEBUG)
        self.log_queue = log_queue
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        fh = logging.FileHandler("logging.log")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        self.zero_coord_count = 0
        self.logger = CustomLogger(logger, self.log_queue)
        self.logger.debug("%s init" % self.__class__.__name__)
        self.screen_processor = sp.StaticImageProcessor(self.screen_capturer)
        self.terrain_analyzer = ta.PathAnalyzer()
        self.keyhandler = km.KeyboardInputManager()
        self.player_manager = pc.PlayerController(self.keyhandler, self.screen_processor, keymap)

        self.last_platform_hash = None
        self.current_platform_hash = None
        self.goal_platform_hash = None

        self.platform_error = 3  # If y value is same as a platform and within 3 pixels of platform border, consider to be on said platform

        # self.rune_model_path = rune_model_dir
        # self.rune_solver = rs.RuneDetector(self.rune_model_path, screen_capturer=self.screen_capturer, key_mgr=self.keyhandler)
        self.rune_platform_offset = 2

        self.loop_count = 0  # How many loops did we loop over?
        self.reset_navmap_loop_count = 10  # every x times reset navigation map, scrambling pathing
        self.navmap_reset_type = 1  # navigation map reset type. 1 for random, -1 for just reset. GETS ALTERNATED

        self.walk_probability = 5
        # This sets random.randint(1, walk_probability) to decide of moonlight slash should just walk instead of glide
        # Probability of walking is (1/walk_probability) * 100

        self.restrict_moonlight_slash_probability = 5

        self.platform_fail_loops = 0
        # How many loops passed and we are not on a platform?

        self.platform_fail_loop_threshold = 10
        # If self.platform_fail_loops is greater than threshold, run unstick()

        self.unstick_attempts = 0
        # If not on platform, how many times did we attempt unstick()?

        self.unstick_attempts_threshold = 5
        # If unstick after this amount fails to get us on a known platform, abort abort.

        self.logger.debug("%s init finished" % self.__class__.__name__)

        self.rune_alert_time = 0

        self.booster_mw_time = 0
        self.adv_bless_time = 0
        self.grim_reaper_time = 0
        self.hammer_time = 0
        self.genesis_time = 0
        self.hs_time = 0
        self.si_time = 0
        self.se_time = 0
        self.pet_feed_time = 0
        self.mana_pot_time = 0
        self.hp_pot_time = 0

        # Platforms
        self.btm_plat = '0ebcbe36'

        # Attacking Mode
        self.attack_direction = None
        self.current_action = 'attack'
        self.next_drop_range = None
        self.next_up_range = None
        self.pressing_arrow_key = None

        # Resting Config
        self.last_rest = None
        self.next_rest = None
        self.resting_spot = None
        self.rest_over = None

    def load_and_process_platform_map(self, path="mapdata.platform"):
        retval = self.terrain_analyzer.load(path)
        self.terrain_analyzer.generate_solution_dict()
        if retval != 0:
            self.logger.debug("Loaded platform data %s" % (path))
        else:
            self.logger.debug("Failed to load platform data %s, terrain_analyzer.load returned 0" % (path))
        return retval

    def distance(self, x1, y1, x2, y2):
        return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)

    def find_current_platform(self):
        current_platform_hash = None

        for key, platform in self.terrain_analyzer.oneway_platforms.items():
            if self.player_manager.y >= min(platform.start_y, platform.end_y) and \
                    self.player_manager.y <= max(platform.start_y, platform.end_y) and \
                    self.player_manager.x >= platform.start_x and \
                    self.player_manager.x <= platform.end_x:
                current_platform_hash = platform.hash
                break

        for key, platform in self.terrain_analyzer.platforms.items():
            if self.player_manager.y == platform.start_y and \
                    self.player_manager.x >= platform.start_x and \
                    self.player_manager.x <= platform.end_x:
                current_platform_hash = platform.hash
                break

        #  Add additional check to take into account imperfect platform coordinates
        for key, platform in self.terrain_analyzer.platforms.items():
            if self.player_manager.y == platform.start_y and \
                    self.player_manager.x >= platform.start_x - self.platform_error and \
                    self.player_manager.x <= platform.end_x + self.platform_error:
                current_platform_hash = platform.hash
                break

        if current_platform_hash:
            return current_platform_hash
        else:
            return 0

    def find_rune_platform(self):
        """
        Checks if a rune exists on a platform and if exists, returns platform hash
        :return: Platform hash, rune_coord_tuple of platform where the rune is located, else 0, 0 if rune does not exist
        """
        self.player_manager.update()
        rune_coords = self.screen_processor.find_rune_marker()
        if rune_coords:
            rune_platform_hash = None
            for key, platform in self.terrain_analyzer.platforms.items():
                if rune_coords[1] >= platform.start_y - self.rune_platform_offset and \
                        rune_coords[1] <= platform.start_y + self.rune_platform_offset and \
                        rune_coords[0] >= platform.start_x and \
                        rune_coords[0] <= platform.end_x:
                    rune_platform_hash = key
            for key, platform in self.terrain_analyzer.oneway_platforms.items():
                if rune_coords[1] >= platform.start_y - self.rune_platform_offset and \
                        rune_coords[1] <= platform.start_y + self.rune_platform_offset and \
                        rune_coords[0] >= platform.start_x and \
                        rune_coords[0] <= platform.end_x:
                    rune_platform_hash = key

            if rune_platform_hash:
                return rune_platform_hash, rune_coords
            else:
                return None
                # return 0, 0
        else:
            # return 0, 0
            return None

    def navigate_to_rune_platform(self):
        """
        Automatically goes to rune_coords by calling find_rune_platform. Update platform information before calling.
        :return: 0
        """
        rune_platform_hash, rune_coords = self.find_rune_platform()
        if not rune_platform_hash:
            return 0
        if self.current_platform_hash != rune_platform_hash:
            rune_solutions = self.terrain_analyzer.pathfind(self.current_platform_hash, rune_platform_hash)
            if rune_solutions:
                self.logger.debug("paths to rune: %s" % (" ".join(x.method for x in rune_solutions)))
                for solution in rune_solutions:
                    if self.player_manager.x < solution.lower_bound[0]:
                        # We are left of solution bounds.
                        self.player_manager.horizontal_move_goal(solution.lower_bound[0])
                    else:
                        # We are right of solution bounds
                        self.player_manager.horizontal_move_goal(solution.upper_bound[0])
                    time.sleep(1)
                    rune_movement_type = solution.method
                    if rune_movement_type == ta.METHOD_DROP:
                        self.player_manager.drop()
                        time.sleep(1)
                    elif rune_movement_type == ta.METHOD_JUMPL:
                        self.player_manager.jumpl_double()
                        time.sleep(0.5)
                    elif rune_movement_type == ta.METHOD_JUMPR:
                        self.player_manager.jumpr_double()
                        time.sleep(0.5)
                    elif rune_movement_type == ta.METHOD_DBLJMP_MAX:
                        self.player_manager.dbljump_max()
                        time.sleep(1)
                    elif rune_movement_type == ta.METHOD_DBLJMP_HALF:
                        self.player_manager.dbljump_half()
                        time.sleep(1)
                time.sleep(0.5)
            else:
                self.logger.debug("could not generate path to rune platform %s from starting platform %s" % (
                    rune_platform_hash, self.current_platform_hash))
        return 0

    def log_skill_usage_statistics(self):
        """
        checks self.player_manager.skill_cast_time and count and logs them if time is greater than threshold
        :return: None
        """
        if not self.player_manager.skill_counter_time:
            self.player_manager.skill_counter_time = time.time()
        if time.time() - self.player_manager.skill_counter_time > 60:
            self.logger.debug("skills casted in duration %d: %d skill/s: %f" % (
                int(time.time() - self.player_manager.skill_counter_time), self.player_manager.skill_cast_counter,
                self.player_manager.skill_cast_counter / int(time.time() - self.player_manager.skill_counter_time)))
            self.player_manager.skill_cast_counter = 0
            self.player_manager.skill_counter_time = time.time()

    def loop(self):
        # Update Screen
        self.update_screen()

        self.current_platform_hash = self.find_current_platform()

        # =========Stuck Check=========
        if self.current_platform_hash == 0:
            self.zero_coord_count += 1
        else:
            self.zero_coord_count = 0

        # self.rune_alert()
        self.lie_detector_alert()

        self.reinitialize_platform_movement()
        # self.unstuck()

        # =========Buff Section=========
        if not self.booster_mw_time or time.time() - self.booster_mw_time > 121:
            print('Casting buff set 1')
            self.booster_mw_time = time.time()
            self.player_manager.castSkill('pgdown', 2)
        if not self.hs_time or time.time() - self.hs_time > 60:
            print('Casting buff set 2')
            self.hs_time = time.time()
            self.player_manager.castSkill('pgup', 2)
        if not self.hp_pot_time or time.time() - self.hp_pot_time > 30:
            print('HP Pot')
            self.hp_pot_time = time.time()
            self.player_manager.castSkill('end', 0.1, sleep_first=True)
        if not self.mana_pot_time or time.time() - self.mana_pot_time > 20:
            print('Mana Pot')
            self.mana_pot_time = time.time()
            self.player_manager.castSkill('CONTROL_L', 0.1, sleep_first=True)
        # if not self.adv_bless_time or time.time() - self.adv_bless_time > 185:
        #     print('Casting Advance Bless')
        #     self.adv_bless_time = time.time()
        #     self.player_manager.castSkill('F9', 0.5, sleep_first=True)
        # if not self.si_time or time.time() - self.si_time > 187:
        #     print('Casting SI')
        #     self.si_time = time.time()
        #     self.player_manager.castSkill('F10', 0.5, sleep_first=True)
        # if not self.se_time or time.time() - self.se_time > 189:
        #     print('Casting SE')
        #     self.se_time = time.time()
        #     self.player_manager.castSkill(';', 0.5, sleep_first=True)
        # if not self.pet_feed_time or time.time() - self.pet_feed_time > 53:
        #     print('Feeding pets')
        #     self.pet_feed_time = time.time()
        #     self.player_manager.castSkill('o', 0.2, sleep_first=True)
        #     self.player_manager.castSkill('o', 0.2, sleep_first=True)
        # if not self.mana_pot_time or time.time() - self.mana_pot_time > 31:
        #     print('Mana pot')
        #     self.mana_pot_time = time.time()
        #     self.player_manager.castSkill('CONTROL_L', 0.1, sleep_first=True)
        # if not self.grim_reaper_time and (
        #         85 <= self.player_manager.x <= 120 and self.current_platform_hash == self.bottom_plat) or \
        #         (time.time() - self.grim_reaper_time > 101) and \
        #         (85 <= self.player_manager.x <= 120 and self.current_platform_hash == self.bottom_plat):
        #     print('Casting grim reaper')
        #     self.grim_reaper_time = time.time()
        #     self.player_manager.castSkill('y', 0.5, sleep_first=True)
        #
        # if not self.genesis_time and (
        #         110 <= self.player_manager.x <= 163 and self.current_platform_hash == self.bottom_plat) or \
        #         (time.time() - self.genesis_time > 101) and \
        #         (110 <= self.player_manager.x <= 163 and self.current_platform_hash == self.bottom_plat):
        #     print('Casting dark genesis')
        #     self.genesis_time = time.time()
        #     self.player_manager.castSkill('f', 0.5, sleep_first=True)

        # =========Attack Section=========
        """Do not proceed beyond this section if mode is not attack"""
        if self.current_action != 'attack':
            return

        if self.attack_direction == 'left':
            self.release_keys()
            self.player_manager.castSkill('right', 0.1, sleep_first=True)
        else:
            self.release_keys()
            self.player_manager.castSkill('left', 0.1, sleep_first=True)
        self.player_manager.attack('v')

        # if self.player_manager.x <= 50:
        #     if not self.player_manager.pressing_arrow_key:
        #         self.release_keys()
        #         self.player_manager.castSkill('left', 0.1, sleep_first=True)
        #
        #     self.player_manager.attack('v')
        # else:
        #     if not self.player_manager.pressing_arrow_key:
        #         self.release_keys()
        #         self.player_manager.castSkill('right', 0.1, sleep_first=True)
        #
        #     self.player_manager.attack('v')

    def update_screen(self):
        self.screen_processor.update_image(set_focus=True)
        # Update Constants
        player_minimap_pos = self.screen_processor.find_player_minimap_marker()

        if not player_minimap_pos:
            return -1
        self.player_manager.update(player_minimap_pos[0], player_minimap_pos[1])

    def go_away_from_portal(self):
        if 72 <= self.player_manager.x <= 76 and (
                self.zero_coord_count >= 5 or self.current_platform_hash == self.rest_plat):
            """
            # Left portal x(72, 76)
            If player is within portal range
            Either walk left or right
            0 -> Walk left
            1 -> Walk right
            """
            walk_movement_choice = random.randint(0, 1)
            self.release_keys()
            if walk_movement_choice:
                print('Going away from portal... walking left.')
                self.player_manager.walkr()
            else:
                print('Going away from portal... walking right.')
                self.player_manager.walkl()
        elif 178 <= self.player_manager.x <= 182:
            """
            # Right portal x(179, 182)
            If within right portal range, only walk left sice platform is on left
            """
            self.release_keys()
            self.player_manager.walkl()

    def go_to_rest_plat(self):
        # Resting Plat Coord x(68, 85)
        if not self.current_platform_hash == self.rest_plat:

            # Portal checking first
            if 72 <= self.player_manager.x <= 76:
                self.go_away_from_portal()
                return

            if self.player_manager.x <= 67:
                """
                If character goes out of bound (to the left) of the resting platform
                1 -> Walk right
                2 -> Walk jump right
                3 -> Teleport right
                """
                right_movement_choice = random.randint(1, 3)

                if right_movement_choice == 1:
                    self.player_manager.walkr()
                elif right_movement_choice == 2:
                    self.player_manager.walkjr()
                else:
                    self.player_manager.teler()
            elif self.player_manager.x >= 85 - 2:
                """
                Walk left with randomize left movement if character is further than resting plat (offset = 2 included)
                1 -> Walk left
                2 -> Walk tele left
                3 -> Walk tele jump left
                4 -> Walk tele attack left
                """

                left_movement_choice = random.randint(1, 4)

                if left_movement_choice == 1:
                    self.player_manager.walkl()
                elif left_movement_choice == 2:
                    self.player_manager.telel()
                elif left_movement_choice == 3:
                    self.player_manager.telejl()
                else:
                    self.player_manager.telecastl()
            elif 68 <= self.player_manager.x < 85 - 2:
                """
                If player is within resting platform range (with offset -2 included)
                If top platform -> Either drop or tele down to the platform
                0 -> Drop
                1 -> Teleport down

                If bottom platform -> Teleport up
                """
                if self.current_platform_hash == self.top_left_plat:
                    drop_movement_choice = random.randint(0, 1)

                    if drop_movement_choice:
                        self.player_manager.teled()
                    else:
                        self.player_manager.drop()
                elif self.current_platform_hash == self.bottom_plat:
                    self.player_manager.teleu()

    def release_keys(self):
        self.player_manager.pressing_arrow_key = False
        self.player_manager.release_keys()

    def reinitialize_platform_movement(self):
        if self.current_action == 'resting':
            """Don't do anything if resting"""
            return

        if self.player_manager.x <= 50:
            self.attack_direction = 'right'
        elif self.player_manager.x >= 150:
            self.attack_direction = 'left'

        # if self.player_manager.x <= 42:
        #     self.attack_direction = 'right'
        #     self.release_keys()
        # if self.player_manager.x >= 144:
        #     self.attack_direction = 'right'
        #     self.release_keys()

        # if self.current_platform_hash == self.bottom_plat and self.attack_direction == 'right':
        #     self.attack_direction = 'left'
        #     self.release_keys()
        #     return
        # if self.current_platform_hash == self.top_plat and self.attack_direction == 'left':
        #     self.attack_direction = 'right'
        #     self.release_keys()
        #     return
        # """
        # ~1% chance to randomize moves
        # """
        # randomize_mode = random.randint(1, 150)
        #
        # """
        # ~1% chance to drop anytime if at top platform
        # """
        # randomize_drop = random.randint(1, 150)
        #
        # if randomize_mode <= 1:
        #
        #     if self.attack_direction == 'left':
        #         print("Move randomzied -> Right!")
        #         self.attack_direction = 'right'
        #     elif self.attack_direction == 'right':
        #         print("Move randomzied -> left!")
        #         self.attack_direction = 'left'
        #
        #     self.next_drop_range = None
        #     self.next_up_range = None
        #
        #     self.release_keys()
        #
        # if randomize_drop <= 1 and \
        #         (self.current_platform_hash == self.top_left_plat or self.current_platform_hash == self.top_right_plat):
        #     print("Dropping randomly!")
        #     self.move_down()
        #     self.release_keys()
        #
        # if self.next_drop_range and self.zero_coord_count <= 5 and self.current_platform_hash == self.bottom_plat:
        #     """
        #     Arrived at bottom platform
        #     """
        #     self.next_drop_range = None
        #
        #     if self.attack_direction == 'left' and self.player_manager.x <= 110:
        #         self.attack_direction = 'right'
        #     elif self.attack_direction == 'right' and self.player_manager.x >= 140:
        #         self.attack_direction = 'left'
        #     print('Direction changed to:', self.attack_direction, '. Releasing all keys...')
        #     self.release_keys()
        # elif self.next_up_range and self.zero_coord_count <= 5 and \
        #         (self.current_platform_hash == self.top_left_plat or self.current_platform_hash == self.top_right_plat):
        #     """
        #     Arrived at top platform
        #     """
        #     self.next_up_range = None
        #
        #     if self.attack_direction == 'left':
        #         self.attack_direction = 'right'
        #     else:
        #         self.attack_direction = 'left'
        #     print('Arrived at next platform:', self.attack_direction, '. Releasing all keys...')
        #     self.release_keys()

    def attack_left(self):
        """
        Attack mode:
        80% Chance: Telecast
        10% Chance: Tele left attack
        10% Chance: Tele jump left attack
        """
        attack_mode = random.randint(1, 100)

        if attack_mode <= 80:
            print('Telecasting')
            self.player_manager.telecast()
        elif 81 <= attack_mode <= 90:
            print('Tele attack')
            self.player_manager.tele_attack()
        elif 91 <= attack_mode <= 100:
            print('Tele jump attack')
            self.player_manager.telejl_attack()

    def attack_right(self):
        """
        Attack mode:
        80% Chance: Telecast
        10% Chance: Tele left attack
        10% Chance: Tele jump left attack
        """

        attack_mode = random.randint(1, 100)

        if attack_mode <= 80:
            print('Telecasting')
            self.player_manager.telecast()
        elif 81 <= attack_mode <= 90:
            print('Tele attack')
            self.player_manager.tele_attack()
            # self.release_keys()
        elif 91 <= attack_mode <= 100:
            print('Tele jump attack')
            self.player_manager.telejr_attack()
            # self.release_keys()

    def move_down(self):
        """
        Move down mode:
        70% Chance: Teleport down
        30% Chance: Drop
        """
        move_down_mode = random.randint(1, 100)
        self.release_keys()
        if move_down_mode <= 30:
            print('Going down by dropping')
            self.player_manager.drop()
        elif move_down_mode >= 70:
            print('Going down by tele jump down')
            self.player_manager.telejd()

    def use_hidden_portal(self, portal_x1, portal_x2):
        still_navigating = True

        while still_navigating:
            self.screen_processor.update_image(set_focus=True)
            player_minimap_pos = self.screen_processor.find_player_minimap_marker()

            self.player_manager.update(player_minimap_pos[0], player_minimap_pos[1])
            if self.player_manager.x > portal_x2:
                print('walking left', self.player_manager.x, portal_x2)
                self.player_manager.walkl()
            elif self.player_manager.x < portal_x1:
                print('walking right', self.player_manager.x, portal_x1)
                self.player_manager.walkr()
            elif portal_x1 <= self.player_manager.x <= portal_x2:
                self.player_manager.castSkill('up', 0.05)
                still_navigating = False
            time.sleep(0.05)

        self.release_keys()

    def unstuck(self, randomize=False):
        if self.zero_coord_count >= 5:
            self.release_keys()
            self.player_manager.teled()
        # if randomize:
        #     """
        #     Gets called when player starts bot from resting platform
        #     50% chance: Tele up
        #     50% chance: Tele down
        #     """
        #     random_move = random.randint(0, 1)
        #
        #     if random_move:
        #         self.player_manager.teled()
        #     else:
        #         self.player_manager.teleju()
        #
        # if self.current_action != 'resting' and (
        #         self.zero_coord_count >= 7 or self.current_platform_hash == self.rest_plat):
        #     print("Trying to unstuck from resting platform")
        #     self.release_keys()
        #     if self.next_up_range:
        #         self.player_manager.teleu()
        #     elif self.next_drop_range:
        #         self.player_manager.telejd()
        #
        # if self.player_manager.x >= 182 and self.current_platform_hash == self.bottom_plat:
        #     """
        #     Additional out of bound check
        #     """
        #     self.release_keys()
        #     self.player_manager.telel()
        #     return
        # if self.player_manager.x >= 178 and self.current_platform_hash == self.bottom_plat:
        #     """
        #     Go left if go out of bound (right)
        #     """
        #     self.player_manager.telel_attack()

        # if self.player_manager.x <= 63 and self.current_platform_hash == self.bottom_plat:
        #     self.player_manager.teleju()

    def abort(self):
        self.keyhandler.reset()
        self.logger.debug("aborted")
        if self.log_queue:
            self.log_queue.put(["stopped", None])

    def rune_alert(self):
        if self.find_rune_platform():
            if self.rune_alert_time <= 0:
                self.rune_alert_time = time.time()
                self.screen_processor.play_rune_alert()
                return

            if round(time.time() - self.rune_alert_time) % 5 == 0:
                self.screen_processor.play_rune_alert()
                return
        else:
            self.rune_alert_time = 0

    def lie_detector_alert(self):
        self.screen_processor.find_violetta()