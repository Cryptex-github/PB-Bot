import discord
from discord.ext import commands, menus
import wavelink
import humanize
import datetime

from dependencies import CustomContext
from config import config


class Track(wavelink.Track):
    """
    Custom track object with a requester attribute.
    """
    __slots__ = ("requester",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args)

        self.requester = kwargs.get("requester")


class Player(wavelink.Player):
    """
    Custom player class.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.now_playing = None
        self.session_started = False
        self.session_chan = None

        self.queue = []
        self.menus = []
        self.volume = 40
        self.queue_position = 0

    async def start(self, ctx):
        self.session_chan = ctx.channel
        await ctx.invoke(ctx.bot.get_command("connect"))
        self.session_started = True
        await self.do_next()

    async def do_next(self):
        try:
            await self.now_playing.delete()
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            pass

        try:
            song = self.queue[self.queue_position]
        except IndexError:  # There are no more songs in the queue.
            await self.destroy()
            return

        self.queue_position += 1

        embed = discord.Embed(title="Now Playing:", description=f"{song}", colour=self.bot.embed_colour)
        embed.set_footer(text=f"Requested by {song.requester}")
        self.now_playing = await self.session_chan.send(embed=embed)
        await self.play(song)

    async def do_previous(self):
        self.queue_position -= 2
        await self.stop()

    async def destroy(self):
        try:
            await self.now_playing.delete()
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            pass

        menus_ = self.menus.copy()
        for menu in menus_:
            menu.stop()

        await super().destroy()


class PlayerMenu(menus.Menu):
    """
    Player menu class.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.embed = None

    async def send_initial_message(self, ctx, channel):
        ctx.player.menus.append(self)
        self.build_embed()
        return await channel.send(embed=self.embed)

    async def build_edit(self):
        self.build_embed()
        await self.message.edit(embed=self.embed)

    def build_embed(self):
        max_song_length = float(f"{self.ctx.player.current.length / 1000:.2f}")
        current_position = float(f"{self.ctx.player.position / 1000:.2f}")
        bar_number = int((int(current_position) / int(max_song_length)) * 20)
        bar = f"\||{bar_number * self.ctx.bot.emoji_dict['red_line']}⚫{(19 - bar_number) * self.ctx.bot.emoji_dict['white_line']}||"
        try:
            coming_up = self.ctx.player.queue[self.ctx.player.queue_position]
        except IndexError:
            coming_up = "None"

        self.embed = discord.Embed(
            title=f"Player for `{self.ctx.guild}`",
            description=
            f"**Status:** `{'Paused' if self.ctx.player.is_paused else 'Playing'}`\n"
            f"**Connected To:** `{self.ctx.guild.get_channel(self.ctx.player.channel_id).name}`\n"
            f"**Volume:** `{self.ctx.player.volume}`\n"
            f"**Equalizer:** `{self.ctx.player.equalizer}`",
            colour=self.ctx.bot.embed_colour
        )
        self.embed.add_field(name="Now Playing:", value=f"{self.ctx.player.current}", inline=False)
        self.embed.add_field(name="Duration:", value=humanize.precisedelta(datetime.timedelta(milliseconds=self.ctx.player.current.length)), inline=False)
        self.embed.add_field(name="Time Elapsed:", value=humanize.precisedelta(datetime.timedelta(milliseconds=self.ctx.player.position)), inline=False)
        self.embed.add_field(name="YT Link:", value=f"[Click Here!]({self.ctx.player.current.uri})", inline=False)
        self.embed.add_field(name="Coming Up...", value=coming_up, inline=False)
        self.embed.add_field(name="Progress", value=bar, inline=False)

    @menus.button("⏮️")
    async def song_previous(self, _):
        await self.ctx.player.do_previous()
        if self.ctx.player.queue_position > len(self.ctx.player.queue) - 1:
            await self.build_edit()

    @menus.button("⏭️")
    async def song_skip(self, _):
        await self.ctx.player.stop()
        if self.ctx.player.queue_position < len(self.ctx.player.queue) - 1:
            await self.build_edit()

    @menus.button("⏯️")
    async def play_pause(self, _):
        await self.ctx.player.set_pause(False if self.ctx.player.paused else True)
        await self.build_edit()

    @menus.button("🔈")
    async def volume(self, _):
        await VolumeMenu(delete_message_after=True).start(self.ctx)
        self.stop()

    @menus.button("ℹ️")
    async def on_menu_info(self, _):
        embed = discord.Embed(
            title="How to use the Player",
            description=
            "⏮️ go back to the previous song\n"
            "⏭️  skip the current song\n" 
            "⏯️  pause and unpause the player\n"
            "🔈 opens the volume bar and closes the player\n"
            "ℹ️  shows this message\n"
            "🔁 refreshes the player\n"
            "⏹️  close the player",
            colour=self.ctx.bot.embed_colour)
        if self.embed.title == "How to use the Player":  # hide the menu info screen
            self.build_embed()
        else:
            self.embed = embed
        await self.message.edit(embed=self.embed)

    @menus.button("🔁")
    async def on_refresh(self, _):
        await self.build_edit()

    @menus.button("⏹️")
    async def on_menu_close(self, _):
        self.stop()


class VolumeMenu(menus.Menu):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.embed = None

    async def send_initial_message(self, ctx, channel):
        ctx.player.menus.append(self)
        self.build_embed()
        return await channel.send(embed=self.embed)

    def build_embed(self):
        volume_bar_number = int(self.ctx.player.volume / 100 * 2)
        volume_bar = [(volume_bar_number - 1) * "🟦"] + [self.ctx.bot.emoji_dict["blue_button"]] + [(20 - volume_bar_number) * "⬜"]
        self.embed = discord.Embed(title="Volume Bar", description="".join(volume_bar), colour=self.ctx.bot.embed_colour)
        self.embed.set_footer(text=f"Current Volume: {self.ctx.player.volume}")

    async def build_edit(self):
        self.build_embed()
        await self.message.edit(embed=self.embed)

    @menus.button("⏮️")
    async def on_volume_down_100(self, _):
        await self.ctx.player.set_volume(self.ctx.player.volume - 100)
        await self.build_edit()

    @menus.button("⏪")
    async def on_volume_down_10(self, _):
        await self.ctx.player.set_volume(self.ctx.player.volume - 10)
        await self.build_edit()

    @menus.button("⬅️")
    async def on_volume_down(self, _):
        await self.ctx.player.set_volume(self.ctx.player.volume - 1)
        await self.build_edit()

    @menus.button("➡️")
    async def on_volume_up(self, _):
        await self.ctx.player.set_volume(self.ctx.player.volume + 1)
        await self.build_edit()

    @menus.button("⏩")
    async def on_volume_up_10(self, _):
        await self.ctx.player.set_volume(self.ctx.player.volume + 10)
        await self.build_edit()

    @menus.button("⏭️")
    async def on_volume_up_100(self, _):
        await self.ctx.player.set_volume(self.ctx.player.volume + 100)
        await self.build_edit()

    @menus.button("ℹ️")
    async def on_menu_info(self, _):
        embed = discord.Embed(
            title="How to use the Volume Bar",
            description=
            "⏮️ decrease the volume by 100\n"
            "⏪ decrease the volume by 10\n"
            "⬅️ decrease the volume by 1\n"
            "➡️ increase the volume by 1\n"
            "⏩ increase the volume by 10\n"
            "⏭️ increase the volume by 100\n"
            "ℹ️ shows this message\n"
            "🔁 refreshes the volume bar\n"
            "⏹️ closes the volume bar",
            colour=self.ctx.bot.embed_colour)
        if self.embed.title == "How to use the Volume Bar":  # hide the menu info screen
            self.build_embed()
        else:
            self.embed = embed
        await self.message.edit(embed=self.embed)

    @menus.button("🔁")
    async def on_refresh(self, _):
        await self.build_edit()

    @menus.button("⏹️")
    async def on_menu_close(self, _):
        self.stop()


class QueueSource(menus.ListPageSource):
    def __init__(self, data, player):
        super().__init__(data, per_page=5)

        self.player = player

    async def format_page(self, menu: menus.MenuPages, page):
        embed = discord.Embed(
            title="Song Queue",
            description="\n".join(
                f"**{number}.** {item}" if number != self.player.queue_position else f"*current song* ﹁\n**{number}.** {item}\n﹂ *current song*"
                for number, item in page) or "Nothing in the queue!",
            colour=menu.ctx.bot.embed_colour)
        if self.get_max_pages() > 0:
            embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


# def dj_check():
#     async def predicate(ctx):
#         if ctx.controller.current_dj is None:  # no dj yet
#             ctx.controller.current_dj = ctx.author
#             return True
#         if ctx.controller.current_dj == ctx.author:
#             return True
#         await ctx.send(f"Only the current DJ ({ctx.controller.current_dj}) can control the current guild's player.")
#         return False
#     return commands.check(predicate)


def is_playing():
    async def predicate(ctx):
        if not ctx.player.is_playing:
            await ctx.send("I am not currently playing anything.")
            return False
        return True
    return commands.check(predicate)

# Controls:

# skip/previous
# play/pause
# volume up/down
# songqueue add/remove
# fastforward
# rewind


class Music(commands.Cog):
    """
    Music commands.
    """
    def __init__(self, bot):
        @property
        def get_player(ctx):
            return bot.wavelink.get_player(ctx.guild.id, cls=Player)

        CustomContext.player = get_player
        self.bot = bot
        bot.loop.create_task(self.start_nodes())

    async def cog_check(self, ctx):
        if not ctx.guild:
            raise commands.NoPrivateMessage
        if not ctx.bot.wavelink.nodes:
            await ctx.send("Music commands aren't ready yet. Try again in a bit.")
            return
        if not ctx.player.is_connected:  # anyone can use commands if the bot isn't connected to a voice channel
            return True
        if not ctx.author.voice:  # not in a voice channel
            await ctx.send("You must be in a voice channel to use this command.")
            return
        if ctx.author.voice.channel.id != ctx.player.channel_id:  # in a voice channel, but not in the same one as the bot
            await ctx.send("You must be in the same voice channel as me to use this command.")
            return
        return True

    async def start_nodes(self):
        await self.bot.wait_until_ready()

        if self.bot.wavelink.nodes:
            previous_nodes = self.bot.wavelink.nodes.copy()
            for node in previous_nodes.values():
                await node.destroy()

        node = await self.bot.wavelink.initiate_node(**config["wavelink_node"])
        node.set_hook(self.on_node_event)

    async def on_node_event(self, event):
        if isinstance(event, (wavelink.TrackEnd, wavelink.TrackException)):
            await event.player.do_next()

    # @commands.Cog.listener()
    # async def on_voice_state_update(self, member, before, after):
    #     if before.channel and not after.channel:  # the member was in a vc and the member left the vc
    #         try:
    #             controller = bot.controllers[member.guild.id]
    #         except KeyError:  # there is no controller for the guild. Therefore there is no dj to check for.
    #             return
    #         if controller.current_dj == member:  # the member was the current dj for the controller for that guild
    #             controller.current_dj = None

    @commands.command()
    async def connect(self, ctx, *, voice_channel: discord.VoiceChannel = None):
        """
        Connects the bot to a voice channel.

        `voice_channel` - The voice channel to connect to. If no voice channel is provided, the bot will try to connect to the voice channel the user is currently in.
        """
        if not voice_channel:
            try:
                voice_channel = ctx.author.voice.channel
            except AttributeError:
                return await ctx.send("Couldn't find a channel to join. Please specify a valid channel or join one.")
        await ctx.player.connect(voice_channel.id)
        await ctx.send(f"Connected to **`{voice_channel.name}`**.")

    @is_playing()
    @commands.command()
    async def player(self, ctx):
        """
        Opens up the player menu.
        """
        await PlayerMenu(delete_message_after=True).start(ctx)

    @commands.group(invoke_without_command=True, aliases=["sq"])
    async def songqueue(self, ctx, limit: int = None):
        """
        View the songqueue.

        `limit` - The amount of songs to get from the queue. Fetches all songs if this is not provided.
        """
        if limit is None:
            source = [(number, track) for number, track in enumerate(ctx.player.queue, start=1)]
        else:
            source = [(number, track) for number, track in enumerate(ctx.player.queue[:limit], start=1)]
        await menus.MenuPages(QueueSource(source, ctx.player)).start(ctx)

    @songqueue.command()
    async def add(self, ctx, *, query: str):
        """
        Alias to `play`.
        """
        await ctx.invoke(ctx.bot.get_command("play"), query=query)

    @songqueue.command()
    async def remove(self, ctx, *, query: str):
        """
        Removes a song from the queue.

        `query` - The song to remove from the queue.
        """
        query_results = await ctx.bot.wavelink.get_tracks(f"ytsearch:{query}")
        if not query_results:
            return await ctx.send(f"Could not find any songs with that query.")
        track = Track(query_results[0].id, query_results[0].info, requester=ctx.author)
        for track_, position in enumerate(ctx.player.queue):
            if str(track_) == str(track):
                ctx.player.queue.remove(track_)
                if position < ctx.player.queue_position:
                    ctx.player.queue_position -= 1
        await ctx.send(f"Removed all songs with the name `{track}` from the queue. Queue length: `{len(ctx.player.queue)}`")

    @commands.command()
    async def play(self, ctx, *, query: str):
        """
        Adds a song to the queue.

        `query` - The song to add to the queue.
        """
        if len(ctx.player.queue) >= 100:
            return await ctx.send("Sorry, only `100` songs can be in the queue at a time.")

        query_results = await ctx.bot.wavelink.get_tracks(f"ytsearch:{query}")
        if not query_results:
            return await ctx.send(f"Could not find any songs with that query.")

        if isinstance(query_results, wavelink.TrackPlaylist):
            for track in query_results.tracks:
                track = Track(track.id, track.info, requester=ctx.author)
                ctx.player.queue.append(track)
            await ctx.send(f"Added playlist `{query_results.data['playlistInfo']['name']}` with `{len(query_results.tracks)}` songs to the queue. Queue length: `{len(ctx.player.queue)}`")
        else:
            track = Track(query_results[0].id, query_results[0].info, requester=ctx.author)
            ctx.player.queue.append(track)
            await ctx.send(f"Added `{track}` to the queue. Queue length: `{len(ctx.player.queue)}`")

        if not ctx.player.session_started:
            await ctx.player.start(ctx)

    @is_playing()
    @commands.command()
    async def resume(self, ctx):
        """
        Resumes the player.
        """
        if not ctx.player.is_paused:
            return await ctx.send("I am already playing!")
        await ctx.player.set_pause(False)
        await ctx.send("Resuming...")

    @is_playing()
    @commands.command()
    async def pause(self, ctx):
        """
        Pauses the player.
        """
        if ctx.player.is_paused:
            return await ctx.send("I am already paused!")
        await ctx.player.set_pause(True)
        await ctx.send("Paused the player.")

    @is_playing()
    @commands.command()
    async def skip(self, ctx):
        """
        Skips the currently playing song.
        """
        await ctx.player.stop()
        await ctx.message.add_reaction("✅")

    @is_playing()
    @commands.command()
    async def previous(self, ctx):
        """
        Stops the currently playing song and plays the previous one.
        """
        await ctx.player.do_previous()
        await ctx.message.add_reaction("✅")

    @commands.command()
    async def volume(self, ctx, volume: int = None):
        """
        Adjusts the players volume.

        `volume` - The new volume.
        """
        if volume is None:
            return await VolumeMenu(delete_message_after=True).start(ctx)
        volume = max(min(volume, 1000), 0)
        await ctx.player.set_volume(volume)
        await ctx.send(f"Set the volume to `{volume}`.")

    @is_playing()
    @commands.command(aliases=["eq", "setequalizer", "seteq"])
    async def equalizer(self, ctx, *, equalizer: str):
        """
        Change the players equalizer.

        `equalizer` - The new equalizer. Available equalizers:

        `flat` - Resets the equalizer to flat.
        `boost` - Boost equalizer. This equalizer emphasizes punchy bass and crisp mid-high tones. Not suitable for tracks with deep/low bass.
        `metal` - Experimental metal/rock equalizer. Expect clipping on bassy songs.
        `piano` - Piano equalizer. Suitable for piano tracks, or tacks with an emphasis on female vocals. Could also be used as a bass cutoff.
        **Source:** https://wavelink.readthedocs.io/en/latest/wavelink.html#equalizer
        """
        equalizers = {
            "flat": wavelink.Equalizer.flat(),
            "boost": wavelink.Equalizer.boost(),
            "metal": wavelink.Equalizer.metal(),
            "piano": wavelink.Equalizer.piano()
        }
        equalizer = equalizer.lower()
        try:
            eq = equalizers[equalizer]
        except KeyError:
            eqs = "\n".join(equalizers)
            return await ctx.send(f"Invalid equalizer provided. Available equalizers:\n\n{eqs}")
        await ctx.player.set_eq(eq)
        await ctx.send(f"Set the equalizer to `{equalizer}`.")

    @is_playing()
    @commands.command(aliases=["fastfwd"])
    async def fastforward(self, ctx, seconds: int):
        """
        Fast forward `x` seconds into the current song.

        `seconds` - The amount of seconds to fast forward.
        """
        seek_position = ctx.player.position + (seconds * 1000)
        await ctx.player.seek(seek_position)
        await ctx.send(f"Fast forwarded `{seconds}` seconds. Current position: `{humanize.precisedelta(datetime.timedelta(milliseconds=seek_position))}`")

    @is_playing()
    @commands.command()
    async def rewind(self, ctx, seconds: int):
        """
        Rewind `n` seconds.

        `seconds` - The amount of seconds to rewind.
        """
        seek_position = ctx.player.position - (seconds * 1000)
        await ctx.player.seek(seek_position)
        await ctx.send(f"Rewinded `{seconds}` seconds. Current position: `{humanize.precisedelta(datetime.timedelta(milliseconds=seek_position))}`")

    @commands.command(aliases=["dc"])
    async def disconnect(self, ctx):
        """
        Disconnects the bot from the voice channel and stops the player.
        """
        channel = ctx.guild.get_channel(ctx.player.channel_id)
        await ctx.player.destroy()
        await ctx.send(f"Disconnected from **`{channel}`**.")


def setup(bot):
    bot.add_cog(Music(bot))
