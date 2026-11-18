function streamGrow(el) {
    let max = 0
    let raf = null
    let ro = null

    const chainOpen = () => !!el.querySelector('.agent-chain-body')

    const eligible = () => Alpine.store('stream').state !== 'idle' && chainOpen()

    const setMin = (value) => {
        Alpine.mutateDom(() => {
            el.style.minHeight = value
        })
    }

    // the element's height without the pin's influence: offsetHeight would
    // include the min-height we set, hiding any real shrinkage
    const naturalHeight = () => {
        let h = 0
        for (const child of el.children) {
            h += child.offsetHeight
        }
        return h
    }

    const apply = () => {
        if (!eligible()) {
            max = 0
            setMin('')
            return
        }

        const height = naturalHeight()
        if (height > max) {
            max = height
        }

        if (max > 0 && el.clientHeight < max) {
            setMin(max + 'px')
        }
    }

    const schedule = () => {
        if (raf !== null) return
        raf = requestAnimationFrame(() => {
            raf = null
            const bodyBefore = el.querySelector('.agent-chain-body')
            apply()
            if (el.querySelector('.agent-chain-body') !== bodyBefore) observeContent()
        })
    }

    const observeContent = () => {
        ro?.disconnect()
        ro = null
        if (typeof ResizeObserver === 'undefined') return
        ro = new ResizeObserver(schedule)
        ro.observe(el)
        const body = el.querySelector('.agent-chain-body')
        if (body) ro.observe(body)
    }

    const isChainNode = (node) => {
        return node.nodeType === 1 && (
            node.classList.contains('agent-chain') ||
            node.classList.contains('agent-chain-body') ||
            node.closest('.agent-chain')
        )
    }

    const mo = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            if (mutation.type !== 'childList') continue

            if (mutation.target.nodeType === 1 && mutation.target.closest('.agent-chain')) {
                schedule()
                return
            }

            for (const node of mutation.addedNodes) {
                if (isChainNode(node)) {
                    schedule()
                    return
                }
            }

            for (const node of mutation.removedNodes) {
                if (isChainNode(node)) {
                    schedule()
                    return
                }
            }
        }
    })

    mo.observe(el, { childList: true, characterData: true, subtree: true })

    observeContent()

    const stop = Alpine.effect(() => {
        void Alpine.store('stream').state
        schedule()
    })

    apply()

    return () => {
        mo.disconnect()
        ro?.disconnect()
        stop()
        if (raf !== null) cancelAnimationFrame(raf)
        el.style.minHeight = ''
    }
}
