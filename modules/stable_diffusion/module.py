# Stable diffusion module: sdcpp, a1111, openai, thenoise.

import core
import channels.webui.api as webui
import aiohttp
import base64
import json
import os
import re
import time
import random
import asyncio

def _swallow_task_result(task):
    # consume a detached task's outcome so asyncio never logs it as
    # never-retrieved (the cancellation path has already answered the UI)
    if not task.cancelled():
        task.exception()

class StableDiffusion(core.module.Module):
    """Lets you or your AI generate images using Stable Diffusion. supports a variety of backends"""
    category = 'media'

    settings = {
        'backend': {
            'description': "Engine: sdcpp, a1111, openai, or thenoise",
            'default': 'sdcpp',
            "type": "select",
            "options": {
                "sdcpp": "stable-diffusion.cpp server or a compatible server such as koboldcpp's image server",
                "openai": "OpenAI API-compatible endpoint, such as lemonade",
                "a1111": "Automatic1111",
                "thenoise": "TheNoise - an image generation server specifically for AMD hardware"
            }
        },
        'URL': {
            'description': 'The address of the engine server',
            'default': '127.0.0.1:8080'
        },
        'model': {
            'description': "Model name (only used by the 'openai' backend; empty = server default)",
            'default': '',
            "depends": {"backend": "openai"}
        },
        'resolution': {
            'description': "The resolution to use for your generated images",
            'default': 'HD',
            'type': 'select',
            'options': {
                'LOW': 'LOW (x0.5) - portrait 256×384, landscape 384×256',
                'SD': 'SD (x1) - portrait 512×768, landscape 768×512',
                'HD': 'HD (x2) - portrait 1024×1536, landscape 1536×1024',
                'QHD': 'QHD (x3) - portrait 1536×2304, landscape 2304×1536',
                '3K': '3K (x4) - portrait 2048×3072, landscape 3072×2048',
                '4K': '4K UHD (x5) - portrait 2560×3840, landscape 3840×2560 (needs a model that handles large resolutions)',
            }
        },
        "cfg_scale": {
            "description": "CFG scale to use for the image generation model. This determines how closely the model should follow the prompt - the lower the cfg, the more creative it will be. Some models (such as z-image turbo) need a very low cfg (like below 2) for them to work properly.",
            "default": 6
        },
        "steps": {
            "description": "Amount of generation steps that should be used",
            "default": 20
        },
        "sampler": {
            "description": "Name of the sampler to use. Leave blank to default to the server's setting",
            "default": ""
        },
        'output_folder': {
            'description': 'Folder where generated images are saved and served from',
            'default': '~/gen_images'
        },
        'push_image': {
            'description': 'Also push each generated image straight into the chat as a separate message. When off (default), the tool only returns an {{sd|token}} tag the AI inserts wherever it wants the picture to appear.',
            'default': False,
            'type': 'boolean'
        },
        'enable_gallery': {
            'description': 'Show the gallery sidebar tab',
            'default': True,
            "depends": "enable_webui_extension"
        },
    }

    # an image's unique id: 7 lowercase alnum chars, encoded as the last
    # dot-part of the filename (<slug>.<token>.png and its
    # <slug>.<token>.json sidecar, or a bare <token>.png for nameless and
    # pre-name files), so the token -> file mapping survives even if every
    # metadata file is ever lost
    TOKEN_RE = re.compile('^[a-z0-9]{7}$')

    # the named resolution tiers, in cycle order for the gallery's
    # quick-setting button (must mirror the 'resolution' select options)
    RESOLUTION_TIERS = ('LOW', 'SD', 'HD', 'QHD', '3K', '4K')

    # the manual gallery generation in flight (from the sidebar form), or
    # None: {'cancel': asyncio.Event, 'job_id': str | None}
    _manual_gen = None

    @property
    def asset_mounts(self):
        # expose the image folder to the webui under /ext-assets/stable_diffusion/gen/
        folder = self.config.get('output_folder')
        if folder:
            folder = os.path.expanduser(folder)
        return {'gen': folder} if folder else {}

    async def on_ready(self):
        self.output_dir = self.asset_mounts.get('gen') or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'webui', 'assets')
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
        # sweep files left by generations killed mid-flight: an empty
        # <token>.png never becomes a real image, and a <token>.json whose
        # picture is gone (or still an empty placeholder) is dead weight
        try:
            for fname in os.listdir(self.output_dir):
                if fname.endswith('.png') and self._stem_token(fname[:-4]):
                    stale = os.path.join(self.output_dir, fname)
                    if os.path.getsize(stale) == 0:
                        os.remove(stale)
                elif fname.endswith('.json') and self._stem_token(fname[:-5]):
                    img = os.path.join(self.output_dir, fname[:-5] + '.png')
                    if not (os.path.exists(img) and os.path.getsize(img) > 0):
                        os.remove(os.path.join(self.output_dir, fname))
        except Exception:
            pass
        # gallery category registry: everything the sidecars know, ready
        # for the system prompt and the dropdowns (it grows live as new
        # categories are recorded)
        self._categories = set()
        self._load_categories()
        self.channel.log(self.name, 'Stable Diffusion Module ready. Backend: {} @ {} | images: {}'.format(
            self.config.get('backend'), self.config.get('URL'), self.output_dir))

    # ---- legacy token manifest (sd_manifest.json) -------------------------
    # metadata now lives in per-image sidecars (<token>.json). the old single
    # manifest is still READ as a fallback so pre-sidecar images keep their
    # captions, but nothing is written to it anymore.

    def _manifest_path(self):
        return os.path.join(self.output_dir, 'sd_manifest.json')

    def _load_manifest(self):
        try:
            with open(self._manifest_path()) as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _new_token(self):
        alphabet = 'abcdefghijklmnopqrstuvwxyz0123456789'
        while True:
            token = ''.join(random.choice(alphabet) for _ in range(7))
            # claim it right away with an empty placeholder file, so two
            # concurrent generations can never pick the same token (the
            # actual bytes are written over it when generation finishes;
            # the route hides the empty placeholder until then)
            try:
                with open(os.path.join(self.output_dir, token + '.png'), 'xb') as f:
                    f.close()
                return token
            except FileExistsError:
                continue

    def _record_image(self, base, meta):
        # the image's metadata sidecar: <base>.json sits next to
        # <base>.png (the base being <slug>.<token>, or a bare <token>)
        # and is the single self-contained home for everything
        # this picture was made with (prompt, negative prompt, resolution,
        # cfg, steps, sampler, seed, backend, date...). atomic write:
        # never leave a half-written sidecar behind
        path = os.path.join(self.output_dir, base + '.json')
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(meta, f, indent=2)
        os.replace(tmp, path)
        self._categories.add(meta.get('category') or 'general')
        return meta

    def _load_categories(self):
        # rebuild the category registry from the sidecars on disk
        try:
            names = os.listdir(self.output_dir)
        except Exception:
            return
        for fname in names:
            if not fname.endswith('.json') or not self._stem_token(fname[:-5]):
                continue
            try:
                with open(os.path.join(self.output_dir, fname)) as f:
                    data = json.load(f)
            except Exception:
                continue
            if isinstance(data, dict) and data.get('category'):
                self._categories.add(str(data['category']))

    def _image_categories(self):
        # 'general' anchors the list like the chat categories do
        cats = set(self._categories)
        cats.add('general')
        return sorted(cats)

    @staticmethod
    def _clean_category(value):
        # one canonical spelling per category: trimmed, lowercased, inner
        # whitespace collapsed; empty means the catch-all
        cat = ' '.join(str(value or '').split()).lower()
        return cat or 'general'

    @staticmethod
    def _slugify(value):
        # a filesystem-safe echo of an image's name: lowercase words joined
        # by single dashes, everything else falling by the wayside, capped
        # so filenames stay readable; '' (no usable name at all) means the
        # picture lives under a plain <token> filename
        slug = re.sub('[^a-z0-9]+', '-', str(value or '').lower()).strip('-')
        return slug[:40]

    def _stem_token(self, stem):
        # the token hiding in a file stem: the last dot-part of
        # '<slug>.<token>', or the bare '<token>' of nameless and pre-name
        # files; '' for anything that is not one of ours
        part = stem.rsplit('.', 1)[-1]
        return part if self.TOKEN_RE.match(part) else ''

    def _base_for_token(self, token):
        # the stem of a stored picture on disk: <slug>.<token> when its
        # file carries the name, plain <token> when it does not; None when
        # no png answers to the token at all
        try:
            for fname in os.listdir(self.output_dir):
                if not fname.endswith('.png'):
                    continue
                stem = fname[:-4]
                if stem == token or stem.endswith('.' + token):
                    return stem
        except Exception:
            pass
        return None

    async def on_system_prompt(self):
        # mirrors the chats module: the line earns its place once picking
        # a category is actually a choice
        cats = self._image_categories()
        if len(cats) > 1:
            return "Available categories to categorise generated images into: {}".format(
                ", ".join(cats))
        return None

    def _current_chat_id(self):
        # the chat in focus when the picture was made: the gallery links
        # the image back to the conversation that spawned it
        try:
            return self.channel.context.chat.get('id') or ''
        except Exception:
            return ''  # a channel without chat context has none

    def _meta_for(self, name, prompt, negative_prompt, seed, width, height,
                  orientation, aspect_ratio, cfg_scale, steps, sampler, backend,
                  chat_id, category):
        # the full recipe of one image, persisted as its sidecar
        return {
            'name': name,
            'chat_id': chat_id,
            'category': category,
            'prompt': prompt,
            'negative_prompt': negative_prompt,
            'seed': seed,
            # the real pixel size: the frontend stamps it on the <img> so
            # lazy loads reserve their box instead of reflowing the page
            'width': width,
            'height': height,
            'orientation': orientation,
            'aspect_ratio': str(aspect_ratio or '').strip(),
            'cfg_scale': cfg_scale,
            'steps': steps,
            # an empty sampler means the server's own default was used;
            # the field is kept either way, the gallery spells it out
            'sampler': sampler,
            'backend': backend,
            'date': time.strftime('%Y-%m-%d %H:%M:%S'),
        }

    async def _finalize_image(self, token, slug, image_bytes, meta):
        # persist + announce: the gallery wall grows the moment the
        # bytes land. the broadcast failing (non-webui channel) must
        # never lose the image itself. the bytes land on the claimed
        # <token>.png placeholder first (that claim is what guarantees
        # token uniqueness), then slide into their named home:
        # <slug>.<token>.png when the picture has a name worth carrying.
        png = os.path.join(self.output_dir, token + '.png')
        with open(png, 'wb') as f:
            f.write(image_bytes)
        base = slug + '.' + token if slug else token
        final = os.path.join(self.output_dir, base + '.png')
        if final != png:
            try:
                os.replace(png, final)
            except OSError:
                base = token  # the name was refused: plain token.png will do
        entry = self._record_image(base, meta)
        entry['url'] = '/ext-assets/stable_diffusion/gen/{}.png'.format(base)
        try:
            await self.channel.websocket_manager.broadcast({
                'type': 'sd_new_image', 'token': token, 'meta': entry})
        except Exception:
            pass  # the frontend map refresh picks it up
        return entry

    def _base_url(self):
        api_url = self.config.get('URL')
        if not api_url.startswith('http'):
            api_url = 'http://' + api_url
        return api_url.rstrip('/')

    def _resolution_for(self, orientation, aspect_ratio=''):
        # (w, h) from the configured tier, the requested orientation and an
        # optional 'W:H' aspect ratio. Base aspect: portrait 512x768,
        # landscape 768x512; a given ratio reshapes the frame while keeping
        # the tier's pixel budget, rounded to SD-friendly multiples of 8.
        # Returns (w, h) or None.
        tiers = {'LOW': 0.5, 'SD': 1, 'HD': 2, 'QHD': 3, '3K': 4, '4K': 5}
        raw = str(self.config.get('resolution') or 'SD').upper().strip()
        multiplier = tiers.get(raw)
        if multiplier is None:
            # legacy numeric setting values ('1'-'5', optionally 'x'-prefixed)
            try:
                multiplier = float(raw.lstrip('X'))
            except ValueError:
                return None
        if multiplier < 0.5:
            return None
        orient = (orientation or 'portrait').lower().strip()
        if orient not in ('portrait', 'landscape'):
            return None
        w, h = int(512 * multiplier), int(768 * multiplier)
        ratio = str(aspect_ratio or '').strip().lower().replace('\u00d7', 'x').replace(':', 'x')
        if ratio:
            parts = ratio.split('x')
            if len(parts) != 2:
                return None
            try:
                rw, rh = float(parts[0]), float(parts[1])
            except ValueError:
                return None
            if rw <= 0 or rh <= 0 or rw / rh < 0.2 or rw / rh > 5:
                return None
            area = (512 * multiplier) * (768 * multiplier)
            w = (area * (rw / rh)) ** 0.5
            h = area / w
            w = max(8, int(round(w / 8)) * 8)
            h = max(8, int(round(h / 8)) * 8)
        # orientation has the final say on tall vs wide, so a ratio that
        # fights it (a wide one asked in portrait) is simply flipped
        if orient == 'portrait' and w > h:
            w, h = h, w
        if orient == 'landscape' and h > w:
            w, h = h, w
        return w, h

    # ---- per-backend generators: each returns raw image bytes ----

    async def _gen_sdcpp(self, session, base, prompt, negative, steps, width, height, cfg, sampler, seed, note=None):
        payload = {
            'prompt': prompt,
            'negative_prompt': negative,
            'width': width,
            'height': height,
            'steps': steps,
            'cfg_scale': cfg,
            'seed': seed,
        }
        if sampler:
            payload['sampling_method'] = sampler
        async with session.post(base + '/sdcpp/v1/img_gen', json=payload) as resp:
            resp.raise_for_status()
            job = await resp.json()
        job_id = job.get('id')
        if not job_id:
            raise RuntimeError('sdcpp did not return a job id')
        if note is not None:
            # hand the job id to the caller (a cancelled manual generation
            # uses it to ask the server to drop the job)
            note['job_id'] = job_id
        deadline = time.time() + 300
        while time.time() < deadline:
            await asyncio.sleep(1)
            async with session.get('{}/sdcpp/v1/jobs/{}'.format(base, job_id),
                                   headers={'Cache-Control': 'no-store'}) as resp:
                resp.raise_for_status()
                job = await resp.json()
            status = job.get('status')
            if status in ('completed', 'succeeded'):
                images = (job.get('result') or {}).get('images') or []
                if not images:
                    raise RuntimeError('sdcpp job finished with no images')
                return base64.b64decode(images[0].get('b64_json', ''))
            if status in ('failed', 'cancelled', 'error'):
                raise RuntimeError('sdcpp job failed: {}'.format(
                    (job.get('error') or {}).get('message', status)))
        raise RuntimeError('sdcpp job timed out')

    # every generator takes the same shape; 'note' is the sdcpp job-handoff
    # dict (a plain dict the caller keeps) and the other engines ignore it
    async def _gen_a1111(self, session, base, prompt, negative, steps, width, height, cfg, sampler, seed, note=None):
        payload = {
            'prompt': prompt,
            'negative_prompt': negative,
            'steps': steps,
            'width': width,
            'height': height,
            'cfg_scale': cfg,
            'seed': seed,
        }
        if sampler:
            payload['sampler_name'] = sampler
        async with session.post(base + '/sdapi/v1/txt2img', json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
        images = data.get('images', [])
        if not images:
            raise RuntimeError('No images returned by the A1111 API.')
        return base64.b64decode(images[0])

    async def _gen_openai(self, session, base, prompt, negative, steps, width, height, cfg, sampler, seed, note=None):
        payload = {
            'prompt': prompt,
            'n': 1,
            'size': '{}x{}'.format(width, height),
            'response_format': 'b64_json',
        }
        model = self.config.get('model')
        if model:
            payload['model'] = model
        # non-standard extras; servers that know them use them, others ignore
        for key, val in (('negative_prompt', negative), ('steps', steps),
                         ('cfg_scale', cfg), ('seed', seed)):
            if val not in ('', -1, None):
                payload[key] = val
        async with session.post(base + '/v1/images/generations', json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
        items = data.get('data', [])
        if not items or not items[0].get('b64_json'):
            raise RuntimeError('OpenAI image API returned no image data.')
        return base64.b64decode(items[0]['b64_json'])

    async def _gen_thenoise(self, session, base, prompt, negative, steps, width, height, cfg, sampler, seed, note=None):
        payload = {
            'prompt': prompt,
            'negative_prompt': negative,
            'steps': steps,
            'width': width,
            'height': height,
            'guidance_scale': cfg,
            'seed': seed,
        }
        s = (sampler or '').lower().replace(' ', '_')
        if s in ('euler', 'er_sde'):
            payload['sampler'] = s
        async with session.post(base + '/text2image', json=payload) as resp:
            resp.raise_for_status()
            return await resp.read()  # raw PNG

    async def _generate_image_internal(self, prompt, negative_prompt='', steps=8, width=1024,
                                       height=1024, cfg_scale=1.0, sampler_name='', seed=-1,
                                       note=None):
        backend = (self.config.get('backend') or 'sdcpp').lower()
        base = self._base_url()
        gen = {
            'sdcpp': self._gen_sdcpp,
            'a1111': self._gen_a1111,
            'sdnext': self._gen_a1111,   # SD.Next speaks A1111
            'openai': self._gen_openai,
            'thenoise': self._gen_thenoise,
        }.get(backend)
        if gen is None:
            return None, "Unknown backend '{}'. Use sdcpp, a1111, openai, or thenoise.".format(backend)
        timeout = aiohttp.ClientTimeout(total=300)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                image_bytes = await gen(session, base, prompt, negative_prompt, steps,
                                        width, height, cfg_scale, sampler_name, seed,
                                        note=note)
            return image_bytes, None
        except Exception as e:
            return None, str(e)

    @core.module.tool
    async def generate_image(self, prompt, name='', negative_prompt='', category='', seed=-1, orientation='portrait', aspect_ratio=''):
        """Generate an image and get an inline tag to place it in your messages.
        The result gives you a tag like {{sd|ab12cd3}}: insert that tag verbatim anywhere in any message you write from now on (also in later turns, also during an adventure game) and the picture appears at that spot. Add a placement tail to float it beside the text: {{sd|ab12cd3|left}} or {{sd|ab12cd3|right}}. The name argument is a short human label for the image (e.g. 'tavern at dusk').
        The category argument files the picture under a gallery category (e.g. 'portraits'): use one of the available image categories when one fits, a new one is created otherwise. Omit it to file under 'general'.
        The orientation argument must be either 'portrait' (tall) or 'landscape' (wide); pick whichever suits the subject. The optional aspect_ratio argument ('W:H', e.g. '1:1', '4:3', '16:9' or '21:9') reshapes the frame away from the default 3:2 while keeping the same pixel budget; orientation always decides tall vs wide, so a plain '16:9' asked in portrait just becomes 9:16.
        The optional negative_prompt argument lists things to keep out of the image (e.g. 'text, watermark, extra fingers').
        The seed used is returned: pass it back with an adjusted prompt to refine this same image. Omit seed (or pass -1) for a brand new image."""
        seed = int(seed)
        if seed < 0:
            seed = random.randint(0, 2**32 - 1)
        orientation = (orientation or 'portrait').lower().strip()
        category = self._clean_category(category)
        parsed = self._resolution_for(orientation, aspect_ratio)

        if parsed is None:
            if orientation not in ('portrait', 'landscape'):
                return self.result("Invalid orientation '{}'. Use 'portrait' or 'landscape'.".format(
                    orientation), success=False)
            if str(aspect_ratio or '').strip():
                return self.result("Invalid aspect ratio '{}'. Use the format 'W:H', e.g. '1:1', '4:3' or '16:9'.".format(
                    aspect_ratio), success=False)
            return self.result("Invalid resolution setting '{}'. Use LOW, SD, HD, QHD, 3K or 4K.".format(
                self.config.get("resolution")), success=False)

        width, height = parsed
        steps = self.config.get("steps")
        cfg_scale = self.config.get("cfg_scale")
        sampler = self.config.get("sampler")
        backend = (self.config.get("backend") or "sdcpp").lower()
        token = self._new_token()
        image_bytes, err = await self._generate_image_internal(
            prompt, negative_prompt,
            steps=steps,
            width=width, height=height,
            cfg_scale=cfg_scale,
            sampler_name=sampler,
            seed=seed
        )

        if err:
            # release the claimed token slot
            try:
                os.remove(os.path.join(self.output_dir, token + '.png'))
            except Exception:
                pass
            return self.result(err, success=False)

        slug = self._slugify(name)
        await self._finalize_image(token, slug, image_bytes, self._meta_for(
            name, prompt, negative_prompt, seed, width, height,
            orientation, aspect_ratio, cfg_scale, steps, sampler, backend,
            self._current_chat_id(), category))

        tag = '{{sd|' + token + '}}'
        tag_left = '{{sd|' + token + '|left}}'
        tag_right = '{{sd|' + token + '|right}}'
        pushed = False
        if self.config.get('push_image'):
            base = slug + '.' + token if slug else token
            url = '/ext-assets/stable_diffusion/gen/{}.png'.format(base)
            html = '<img src="{}" alt="{}" style="max-width: 100%; height: auto; border-radius: 8px; margin-top: 10px;">'.format(url, name or token)
            await self.channel.push({'role': 'assistant', 'content': html})
            pushed = True

        return ('Image generated. To show it, insert this tag verbatim anywhere in your reply: {} '
                '(placement tails also work: {} or {}). The tag keeps working in any later message. '
                'Seed used: {} - pass seed={} with an adjusted prompt to refine this same image; '
                'omit seed for a brand new one.{}').format(
            tag, tag_left, tag_right,
            seed, seed, ' Image was also pushed to the chat.' if pushed else '')

    # ---- manual generation: the gallery sidebar's own generate form ------

    async def _generate_for_gallery(self, prompt, negative_prompt, state, category,
                                    orientation='portrait'):
        # one manual generation with config-driven defaults (orientation,
        # resolution tier, cfg, steps, sampler). when the cancel flag is
        # raised while the engine works, the finished picture is reaped
        # without ever being saved or announced.
        parsed = self._resolution_for(orientation, '')
        if parsed is None:
            return self.result("Invalid resolution setting '{}'. Use LOW, SD, HD, QHD, 3K or 4K.".format(
                self.config.get('resolution')), success=False)
        width, height = parsed
        steps = self.config.get('steps')
        cfg_scale = self.config.get('cfg_scale')
        sampler = self.config.get('sampler')
        backend = (self.config.get('backend') or 'sdcpp').lower()
        seed = random.randint(0, 2**32 - 1)
        token = self._new_token()
        image_bytes, err = await self._generate_image_internal(
            prompt, negative_prompt,
            steps=steps, width=width, height=height,
            cfg_scale=cfg_scale, sampler_name=sampler,
            seed=seed, note=state
        )
        png = os.path.join(self.output_dir, token + '.png')
        if err or state['cancel'].is_set():
            # failed, or cancelled while the engine was still working:
            # release the token slot and drop whatever came back
            try:
                os.remove(png)
            except Exception:
                pass
            if err:
                return self.result(err, success=False)
            return {'cancelled': True}
        await self._finalize_image(token, '', image_bytes, self._meta_for(
            '', prompt, negative_prompt, seed, width, height,
            orientation, '', cfg_scale, steps, sampler, backend,
            self._current_chat_id(), category))
        return {'cancelled': False, 'token': token, 'seed': seed}

    async def _interrupt_backend(self, state):
        # best-effort engine-side stop: our wait is already gone, this just
        # keeps the engine from finishing work nobody wants. servers without
        # such an endpoint keep rendering into the void - the result gets
        # discarded either way, so every failure here is silent on purpose.
        backend = (self.config.get('backend') or 'sdcpp').lower()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                if backend in ('a1111', 'sdnext'):
                    await session.post(self._base_url() + '/sdapi/v1/interrupt')
                elif backend == 'sdcpp' and state.get('job_id'):
                    await session.request('DELETE', '{}/sdcpp/v1/jobs/{}'.format(
                        self._base_url(), state['job_id']))
        except Exception:
            pass

    @webui.route('generate', method='POST')
    async def _route_generate(self, body=None, query=None):
        """One manual gallery generation: {prompt, negative_prompt?, category?,
        orientation?}. The cancel flag races the generation, so Cancel
        answers the UI the moment it lands; a generation that finishes
        after being cancelled discards its picture instead of showing up
        on the wall."""
        if self._manual_gen is not None:
            return self.result("A manual generation is already running.", success=False)
        body = body or {}
        prompt = str(body.get('prompt') or '').strip()
        if not prompt:
            return self.result("A prompt is required.", success=False)
        negative = str(body.get('negative_prompt') or '')
        category = self._clean_category(body.get('category'))
        orientation = ('landscape'
                       if str(body.get('orientation') or '').lower() == 'landscape'
                       else 'portrait')
        state = {'cancel': asyncio.Event(), 'job_id': None}
        self._manual_gen = state
        task = asyncio.create_task(self._generate_for_gallery(
            prompt, negative, state, category, orientation))
        waiter = asyncio.create_task(state['cancel'].wait())
        try:
            done, _ = await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            waiter.cancel()
        if task in done:
            self._manual_gen = None
            return task.result()
        # cancelled: free the slot right away; the detached task notices
        # the flag when the engine call returns and reaps the placeholder
        self._manual_gen = None
        task.add_done_callback(_swallow_task_result)
        await self._interrupt_backend(state)
        return {'cancelled': True}

    @webui.route('generate_cancel', method='POST')
    async def _route_generate_cancel(self, body=None, query=None):
        """Raise the cancel flag of the manual generation in flight."""
        state = self._manual_gen
        if state is None:
            return {'cancelled': False}
        state['cancel'].set()
        return {'cancelled': True}

    @webui.route('generate_status')
    async def _route_generate_status(self, body=None, query=None):
        """Is a manual generation in flight? (lets a reloaded page resync
        its generating.. indicator)"""
        return {'running': self._manual_gen is not None}

    @webui.route('images')
    async def _route_images(self, body=None, query=None):
        """token -> metadata (prompt, seed, resolution, cfg, sampler, ...)
        plus url for every finished image. self-healing: tokens come from
        the image files themselves; each one is decorated by its
        <token>.json sidecar, with the legacy sd_manifest.json filling in
        whatever the sidecar lacks (pre-sidecar images)."""
        images = {}
        try:
            legacy = self._load_manifest()
            for fname in sorted(os.listdir(self.output_dir)):
                stem, ext = os.path.splitext(fname)
                if ext.lower() != '.png':
                    continue
                token = self._stem_token(stem)
                if not token:
                    continue
                if os.path.getsize(os.path.join(self.output_dir, fname)) == 0:
                    continue  # placeholder for a generation still running
                entry = dict(legacy.get(token) or {})
                try:
                    with open(os.path.join(self.output_dir, stem + '.json')) as f:
                        sidecar = json.load(f)
                    if isinstance(sidecar, dict):
                        entry.update(sidecar)
                except Exception:
                    pass  # a missing/broken sidecar just decorates less
                if entry.get('category'):
                    # a sidecar scanned here may know a category the
                    # registry has not met yet (folder edited externally)
                    self._categories.add(str(entry['category']))
                entry['url'] = '/ext-assets/stable_diffusion/gen/{}.png'.format(stem)
                images[token] = entry
        except Exception:
            pass
        return {'images': images, 'categories': self._image_categories()}

    @webui.route('meta_update', method='POST')
    async def _route_meta_update(self, body=None, query=None):
        """Rename an image or move it to another category.

        Body: {token, name?, category?} - exactly these two fields are
        ever touched: prompt, seed and the rest of the recipe stay the
        engraved truth. Rewrites the sidecar atomically (creating one for
        pre-sidecar images), renames the files so their <slug> keeps
        echoing the picture's current name, and broadcasts sd_image_meta
        so every open tab repaints: modal rows, wall tiles and the
        category dropdowns."""
        body = body or {}
        token = str(body.get('token') or '').strip().lower()
        if not self.TOKEN_RE.match(token):
            return self.result('No image with that token.', success=False)
        base = self._base_for_token(token)
        if base is None:
            return self.result('No image with that token.', success=False)
        if 'name' not in body and 'category' not in body:
            return self.result('Nothing to update.', success=False)
        meta = {}
        try:
            with open(os.path.join(self.output_dir, base + '.json')) as f:
                data = json.load(f)
            if isinstance(data, dict):
                meta = data
        except Exception:
            pass  # pre-sidecar image: this edit writes its first sidecar
        if 'name' in body:
            meta['name'] = ' '.join(str(body.get('name') or '').split())[:120]
        if 'category' in body:
            meta['category'] = self._clean_category(body.get('category'))
        # the files keep echoing the name: slide <slug>.<token>.* to its
        # new slug (or down to a bare <token> when the name became blank)
        slug = self._slugify(meta.get('name'))
        new_base = slug + '.' + token if slug else token
        if new_base != base and not os.path.exists(
                os.path.join(self.output_dir, new_base + '.png')):
            try:
                os.replace(os.path.join(self.output_dir, base + '.png'),
                           os.path.join(self.output_dir, new_base + '.png'))
            except OSError:
                new_base = base  # the move was refused: stay where we are
            else:
                try:
                    os.remove(os.path.join(self.output_dir, base + '.json'))
                except OSError:
                    pass
        self._record_image(new_base, meta)
        # the announced entry carries everything the views know this image
        # by: legacy manifest fields first, the fresh sidecar over them
        entry = dict(self._load_manifest().get(token) or {})
        entry.update(meta)
        entry['url'] = '/ext-assets/stable_diffusion/gen/{}.png'.format(new_base)
        try:
            await self.channel.websocket_manager.broadcast({
                'type': 'sd_image_meta', 'token': token, 'meta': entry})
        except Exception:
            pass  # the frontend map refresh picks it up
        return {'success': True, 'meta': entry}

    @webui.route('delete_image', method='POST')
    async def _route_delete_image(self, body=None, query=None):
        """Delete an image for good: its png and its sidecar, whatever
        slug their filename carries.

        Body: {token}. Announces sd_image_gone so every open tab prunes
        the tile from its wall right away."""
        body = body or {}
        token = str(body.get('token') or '').strip().lower()
        if not self.TOKEN_RE.match(token):
            return self.result('No image with that token.', success=False)
        base = self._base_for_token(token)
        if base is None:
            return self.result('No image with that token.', success=False)
        for ext in ('.png', '.json'):
            try:
                os.remove(os.path.join(self.output_dir, base + ext))
            except FileNotFoundError:
                pass
            except Exception as e:
                return self.result('Could not delete: {}'.format(e), success=False)
        try:
            await self.channel.websocket_manager.broadcast({
                'type': 'sd_image_gone', 'token': token})
        except Exception:
            pass  # the frontend map refresh picks it up
        return {'success': True}

    @webui.route('resolution')
    async def _route_resolution(self, body=None, query=None):
        """Current resolution tier for the gallery quick-setting."""
        raw = str(self.config.get('resolution') or 'SD').upper().strip()
        return {'resolution': raw if raw in self.RESOLUTION_TIERS else 'SD'}

    @webui.route('resolution_set', method='POST')
    async def _route_resolution_set(self, body=None, query=None):
        """Quick-set the resolution tier from the gallery header: {tier}.

        In-memory only: the next generation uses it right away, while the
        settings page keeps whatever is actually saved on disk."""
        body = body or {}
        tier = str(body.get('tier') or '').upper().strip()
        if tier not in self.RESOLUTION_TIERS:
            return self.result("Unknown resolution tier '{}'.".format(tier), success=False)
        self.config.set('resolution', tier)
        return {'resolution': tier}

    @core.module.command('sd_status', help='Checks if the SD backend is reachable')
    async def sd_status_command(self, args):
        base = self._base_url()
        backend = (self.config.get('backend') or 'sdcpp').lower()
        probes = {
            'sdcpp': base + '/sdcpp/v1/capabilities',
            'a1111': base + '/sdapi/v1/options',
            'sdnext': base + '/sdapi/v1/options',
            'openai': base + '/v1/models',
            'thenoise': base + '/health',
        }
        probe = probes.get(backend)
        if probe is None:
            return "Unknown backend '{}'.".format(backend)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(probe) as resp:
                    resp.raise_for_status()
                    try:
                        info = await resp.json()
                    except Exception:
                        info = '(no json)'
            return 'SD backend ({}) is online: {}'.format(backend, info)
        except Exception as e:
            return 'SD backend is offline or unreachable: {}'.format(str(e))
