import discord
import subprocess
import platform
from datetime import datetime, timedelta, timezone
import json

bot = discord.Bot()

with open("config/config.json", "r") as config_file:
    config = json.load(config_file)

def get_current_time():
    local_timezone = timezone(timedelta(hours=config["timezone_offset"]))
    current_time = datetime.now(local_timezone).strftime("%I:%M %p - %d/%m/%Y")
    return current_time

async def get_container_names(ctx: discord.AutocompleteContext):
    try:
        context = ctx.options.get("context", "default")
        result = subprocess.check_output(['docker', f'--context={context}', 'ps', '--all', '--format', '{{.Names}}'], text=True)
        container_names = result.split('\n')
        container_names = [name for name in container_names if name]
        return container_names
    except subprocess.CalledProcessError:
        return []

@bot.event
async def on_ready():
    activity_type = config["status"]["type"]
    activity_message = config["status"]["message"]

    if activity_type == "playing":
        activity = discord.Game(name=activity_message)
    elif activity_type == "listening":
        activity = discord.Activity(type=discord.ActivityType.listening, name=activity_message)
    elif activity_type == "watching":
        activity = discord.Activity(type=discord.ActivityType.watching, name=activity_message)
    else:
        activity = None

    await bot.change_presence(activity=activity)
    print("Bot online!")

docker_management = bot.create_group("docker", "Manage Docker containers")

@docker_management.command(description="Execute Docker container management commands.")
async def execute(ctx,
    action: discord.Option(str, choices=['start', 'stop', 'restart', 'pause', 'unpause', 'delete']),
    container_name: discord.Option(str, autocomplete=discord.utils.basic_autocomplete(get_container_names)),
    context: discord.Option(str, description="Docker context", default="default")
):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return

    try:
        await ctx.defer()
        docker_cmd = ['docker', f'--context={context}']
        response = ""

        if action == "start":
            subprocess.check_output(docker_cmd + ['start', container_name])
            response = f"Container `{container_name}` has been started."
        elif action == "stop":
            subprocess.check_output(docker_cmd + ['stop', container_name])
            response = f"Container `{container_name}` has been stopped."
        elif action == "restart":
            subprocess.check_output(docker_cmd + ['restart', container_name])
            response = f"Container `{container_name}` has been restarted."
        elif action == "pause":
            subprocess.check_output(docker_cmd + ['pause', container_name])
            response = f"Container `{container_name}` has been paused."
        elif action == "unpause":
            subprocess.check_output(docker_cmd + ['unpause', container_name])
            response = f"Container `{container_name}` has been unpaused."
        elif action == "delete":
            status = subprocess.check_output(docker_cmd + ['inspect', '-f', '{{.State.Status}}', container_name], text=True).strip()
            if status == 'running':
                await ctx.respond(f"Container `{container_name}` is still running. Please stop it before deleting.")
                return
            subprocess.check_output(docker_cmd + ['rm', container_name])
            response = f"Container `{container_name}` has been deleted."

        embed = discord.Embed(title="**__Docker Management__**", description=response, color=discord.Colour.blurple())
        embed.set_footer(text=get_current_time())
        await ctx.respond(embed=embed)

    except subprocess.CalledProcessError as e:
        await ctx.respond(f"Error executing Docker command: {e}")

@docker_management.command(description="Manage Docker images.")
async def images(ctx,
    action: discord.Option(str, choices=['list', 'pull', 'remove']),
    image_name: discord.Option(str) = None,
    context: discord.Option(str, description="Docker context", default="default")
):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return

    try:
        await ctx.defer()
        docker_cmd = ['docker', f'--context={context}']
        response = ""

        if action == "list":
            result = subprocess.check_output(docker_cmd + ['images', '--format', '{{.Repository}}:{{.Tag}}\t{{.Size}}'], text=True)
            lines = [line.split('\t') for line in result.split('\n') if line]
            response = "\n".join([f"**{img}** - Size: {size}" for img, size in lines])
        elif action == "pull" and image_name:
            subprocess.check_output(docker_cmd + ['pull', image_name])
            response = f"Image `{image_name}` has been pulled."
        elif action == "remove" and image_name:
            subprocess.check_output(docker_cmd + ['rmi', image_name])
            response = f"Image `{image_name}` has been removed."
        else:
            await ctx.respond("Please provide a valid image name.")
            return

        embed = discord.Embed(title="**__Docker Image Management__**", description=response, color=discord.Colour.blurple())
        embed.set_footer(text=get_current_time())
        await ctx.respond(embed=embed)

    except subprocess.CalledProcessError as e:
        await ctx.respond(f"Error executing Docker command: {e}")

@docker_management.command(description="Prune Docker images.")
async def prune(ctx,
    all: discord.Option(bool, description="Prune all images", required=True),
    context: discord.Option(str, description="Docker context", default="default")
):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return

    try:
        await ctx.defer()
        docker_cmd = ['docker', f'--context={context}', 'image', 'prune', '-f']
        if all:
            docker_cmd.append('-a')

        subprocess.check_output(docker_cmd)
        response = "Unused Docker images have been pruned."

        embed = discord.Embed(title="**__Docker Image Pruning__**", description=response, color=discord.Colour.blurple())
        embed.set_footer(text=get_current_time())
        await ctx.respond(embed=embed)

    except subprocess.CalledProcessError as e:
        await ctx.respond(f"Error executing Docker command: {e}")

@bot.slash_command(guild_ids=config["guild_ids"], description="List All Docker Containers")
async def list(ctx,
    context: discord.Option(str, description="Docker context", default="default")
):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return

    try:
        await ctx.defer()
        docker_cmd = ['docker', f'--context={context}', 'ps', '--all', '--format', '{{.Names}}\t{{.Status}}']
        result = subprocess.check_output(docker_cmd, text=True)
        containers = [line.split('\t') for line in result.split('\n') if line]

        online = [f"**{name}**: `{status}`" for name, status in containers if "Up" in status]
        offline = [f"**{name}**: `{status}`" for name, status in containers if "Up" not in status]

        embed = discord.Embed(title="**__Docker Container(s) Status__**", color=discord.Colour.blurple())
        if online:
            embed.add_field(name=":green_circle: **__Online__**", value="\n".join(online), inline=False)
        if offline:
            embed.add_field(name=":red_circle: **__Offline__**", value="\n".join(offline), inline=False)

        embed.set_footer(text=get_current_time())
        await ctx.respond(embed=embed)

    except subprocess.CalledProcessError as e:
        await ctx.respond(f"Error retrieving Docker containers: {e}")

@bot.slash_command(guild_ids=config["guild_ids"], description="Ping the bot.")
async def ping(ctx):
    await ctx.respond("`\U0001F3D3 Pong!`")

@bot.slash_command(guild_ids=config["guild_ids"], description="Get system uptime.")
async def uptime(ctx):
    try:
        await ctx.defer()
        if platform.system().lower() == 'linux':
            result = subprocess.check_output(['uptime', '-p'], text=True)
        elif platform.system().lower() == 'darwin':
            result = subprocess.check_output(['uptime'], text=True)
        else:
            result = "System uptime command not supported."

        embed = discord.Embed(title="**__System Uptime__**", description=f"**Uptime:** `{result.strip()}`", color=discord.Colour.blurple())
        embed.set_footer(text=get_current_time())
        await ctx.respond(embed=embed)

    except subprocess.CalledProcessError as e:
        await ctx.respond(f"Error retrieving system uptime: {e}")

bot.run(config["token"])
